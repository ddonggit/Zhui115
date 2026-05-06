"""Zhui115 定时调度模块

负责：
  1. 定时检查所有启用的 RSS 源
  2. 将新链接提交到 115 离线下载
  3. 重试失败的任务
  4. 定期清理旧数据

防 Cloudflare 策略：
  - 源间随机延迟 2-6 秒，避免同时请求
  - 定时器加入随机抖动（±20%），避免整点触发
  - 源级失败计数，反复失败则跳过整轮
"""

import logging
import random
import re
import time
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from .config import load_global, load_sources, save_global, update_source
from .db import (
    add_episode, episode_exists, add_offline_task, update_offline_task,
    get_pending_tasks, get_retryable_tasks, add_retry, remove_retry,
    add_history, vacuum as db_vacuum, get_task_stats, get_conn,
)
from .rss import parse_rss
from .offline115 import get_client, submit_urls, get_save_dir_id, query_quota, extract_info_hash
from .notifier import notify_success, notify_failure, notify_rss_failure
from p115client import check_response

logger = logging.getLogger("zhui115.scheduler")

# 全局调度器
scheduler = BackgroundScheduler(daemon=True)
_running = False

# 源级状态跟踪（进程内记忆，容器重启后重置）
_source_state: dict[str, dict] = {}


def _init_source_state(name: str) -> dict:
    """初始化单个源的运行状态"""
    st = _source_state.get(name)
    if st is None:
        st = {
            "fail_count": 0,        # 连续失败次数
            "last_success": None,   # 最后一次成功时间
            "consecutive_cf": 0,    # 连续 Cloudflare 拦截次数
            "notified_fail": False,  # 是否已发送失败通知（避免重复）
        }
        _source_state[name] = st
    return st


def start():
    """启动定时调度"""
    global _running
    if _running:
        return
    _running = True

    cfg = load_global()
    interval = max(1, cfg.get("check_interval", 30))
    # 20% 抖动（秒），让每次触发时间不固定
    jitter_sec = max(10, int(interval * 60 * 0.2))

    scheduler.add_job(
        check_all_sources, "interval", minutes=interval,
        id="check_rss", name="检查 RSS 源", replace_existing=True,
        jitter=jitter_sec,
    )
    scheduler.add_job(
        process_retry_queue, "interval", minutes=1,
        id="process_retry", name="处理重试队列", replace_existing=True,
        jitter=15,
    )
    scheduler.add_job(
        sync_offline_status, "interval", minutes=10,
        id="sync_status", name="同步离线状态", replace_existing=True,
        jitter=60,
    )

    # 每天凌晨清理一次
    scheduler.add_job(
        do_vacuum, "cron", hour=3, minute=0,
        id="vacuum", name="数据清理", replace_existing=True,
    )

    scheduler.start()
    logger.info("定时调度已启动，RSS 检查间隔 %d 分钟（±%ds 抖动）",
                interval, jitter_sec)


def stop():
    """停止定时调度"""
    global _running
    if scheduler.running:
        scheduler.shutdown(wait=False)
    _running = False
    logger.info("定时调度已停止")


def reschedule_check():
    """根据当前配置重新调度 RSS 检查间隔"""
    cfg = load_global()
    interval = max(1, cfg.get("check_interval", 30))
    jitter_sec = max(10, int(interval * 60 * 0.2))
    if scheduler.running:
        scheduler.add_job(
            check_all_sources, "interval", minutes=interval,
            id="check_rss", name="检查 RSS 源", replace_existing=True,
            jitter=jitter_sec,
        )
        logger.info("RSS 检查间隔已更新为 %d 分钟（±%ds 抖动）",
                    interval, jitter_sec)
    else:
        logger.warning("调度器未运行，无法更新间隔")


def check_all_sources():
    """检查所有启用的 RSS 源

    每个源之间加入随机延迟，防止被 Cloudflare 识别为批量请求。
    连续失败的源会被暂时跳过。
    """
    cfg = load_global()
    sources = load_sources()
    quota = None
    client = get_client()
    save_dir_id = get_save_dir_id(client) if client else 0

    enabled_sources = [s for s in sources if s.get("enabled", True) and s.get("url")]
    logger.info("开始检查 %d 个 RSS 源...", len(enabled_sources))

    for idx, src in enumerate(enabled_sources):
        name = src["name"]
        url = src["url"]
        st = _init_source_state(name)

        # ---- 跳过策略 ----
        # 连续 Cloudflare 拦截 >3 次 → 跳过本轮
        if st["consecutive_cf"] >= 3:
            logger.warning("源 %s 连续 %d 次触发 Cloudflare，跳过本轮",
                           name, st["consecutive_cf"])
            add_history("rss_skip", f"{name}: 连续触发Cloudflare，跳过本轮")
            if not st.get("notified_fail"):
                notify_rss_failure(name, "连续触发 Cloudflare 挑战，源可能已失效")
                st["notified_fail"] = True
            continue
        # 连续失败 >5 次 → 跳过本轮
        if st["fail_count"] >= 5:
            logger.warning("源 %s 连续失败 %d 次，跳过本轮",
                           name, st["fail_count"])
            add_history("rss_skip", f"{name}: 连续失败{st['fail_count']}次，跳过本轮")
            if not st.get("notified_fail"):
                notify_rss_failure(name, f"连续 {st['fail_count']} 次获取失败，源可能已失效")
                st["notified_fail"] = True
            continue

        # ---- 源间随机延迟（最后一个源不必延迟） ----
        if idx > 0:
            delay = random.uniform(2, 6)
            logger.debug("源间延迟 %.1f 秒", delay)
            time.sleep(delay)

        logger.info("检查 RSS 源: %s", name)
        try:
            items = parse_rss(url)
        except RuntimeError as e:
            msg = str(e)
            logger.error("解析 RSS 源 %s 失败: %s", name, msg)
            add_history("rss_error", f"{name}: {msg}")
            # Cloudflare 拦截标记
            if "Cloudflare" in msg or "拦截" in msg:
                st["consecutive_cf"] += 1
            else:
                st["consecutive_cf"] = 0
            st["fail_count"] += 1
            continue

        # 成功恢复
        st["fail_count"] = 0
        st["consecutive_cf"] = 0
        st["notified_fail"] = False
        st["last_success"] = datetime.now(timezone.utc)

        if not items:
            logger.info("RSS 源 %s 无新条目", name)
            continue

        # 检查配额（复用外层已创建的 client，避免重复创建）
        if quota is None and client:
            try:
                quota_resp = check_response(client.offline_quota_info())
                quota = {"ok": True, "data": quota_resp}
            except Exception as e:
                quota = {"ok": False, "error": str(e)}
        if quota.get("ok") and quota["data"].get("quota", 0) <= 0:
            logger.warning("115 离线配额不足，跳过提交")
            add_history("quota_warning", "115 离线配额不足")
            break

        new_links = []
        for item in items:
            if _should_skip(item, src):
                continue

            link_hash = item["link_hash"]
            if episode_exists(link_hash):
                continue

            # 记录剧集
            add_episode(
                source_name=name,
                link_hash=link_hash,
                title=item["title"],
                link=item["link"],
                episode=item["episode_num"],
                season=item["season_num"],
            )

            # 添加到离线任务
            task_id = add_offline_task(
                source_name=name,
                title=item["title"],
                link=item["link"],
                link_hash=link_hash,
                episode_num=item.get("episode_num", 0),
                season_num=item.get("season_num", 0),
                quality=item.get("quality", ""),
                image_url=item.get("image_url", ""),
            )
            new_links.append({
                "task_id": task_id,
                "link": item["link"],
                "title": item["title"],
                "episode_num": item["episode_num"],
            })

        # 批量提交
        max_ep = 0
        if new_links:
            max_ep = _submit_batch(new_links, save_dir_id, name)

        # 更新源的 last_episode（自动跟进集数）
        if src.get("auto_episode") and max_ep > src.get("last_episode", 0):
            update_source(src["name"], {"last_episode": max_ep})

    add_history("check_complete", f"检查完成，共 {len(enabled_sources)} 个源")


def _should_skip(item: dict, src: dict) -> bool:
    """判断条目是否应该被跳过"""
    title = item["title"]
    use_regex = src.get("regex_filter", False)

    # 排除关键词
    for kw in src.get("filter_exclude", []):
        if not kw:
            continue
        if use_regex:
            try:
                if re.search(kw, title):
                    return True
            except re.error:
                pass
        elif kw.lower() in title.lower():
            return True

    # 包含关键词（如果设置了，则必须包含）
    incl_kws = src.get("filter_keywords", [])
    if incl_kws:
        matched = False
        for kw in incl_kws:
            if not kw:
                continue
            if use_regex:
                try:
                    if re.search(kw, title):
                        matched = True
                        break
                except re.error:
                    pass
            elif kw.lower() in title.lower():
                matched = True
                break
        if not matched:
            return True

    # 季数过滤
    src_season = src.get("season", 0)
    if src_season and item["season_num"] and item["season_num"] != src_season:
        return True

    # 集数过滤（自动跟进）
    if src.get("auto_episode"):
        last_ep = src.get("last_episode", 0)
        if item["episode_num"] and item["episode_num"] <= last_ep:
            return True

    # 集数范围过滤（手动指定起止集数）
    ep_num = item["episode_num"]
    ep_from = src.get("episode_from", 0)
    ep_to = src.get("episode_to", 0)
    if ep_from > 0 or ep_to > 0:
        if not ep_num:
            return True  # 设置了集数范围但无法识别 → 跳过（如剧场版/OVA）
        if ep_from > 0 and ep_num < ep_from:
            return True
        if ep_to > 0 and ep_num > ep_to:
            return True

    return False


def _submit_batch(new_links: list, save_dir_id: int, source_name: str) -> int:
    """批量提交离线下载，返回最大集数"""
    urls = [item["link"] for item in new_links]
    max_ep = max((item["episode_num"] for item in new_links), default=0)
    logger.info("提交 %d 个链接到 115 离线下载...", len(urls))

    result = submit_urls(urls, save_dir_id)

    if result["ok"]:
        data = result["data"]
        # 提取 info_hash：可能返回字符串或列表，也可能嵌套在 data 内
        info_hashes = data.get("info_hash") or data.get("data", {}).get("info_hash") or []
        if isinstance(info_hashes, str):
            info_hashes = [info_hashes]

        for i, item in enumerate(new_links):
            info_hash = info_hashes[i] if i < len(info_hashes) else ""
            # 如果 115 响应没返回 info_hash，从磁力链接中提取
            if not info_hash:
                info_hash = extract_info_hash(item["link"])
            update_offline_task(
                item["task_id"], status="已提交",
                info_hash=info_hash,
                message="已提交到115",
            )
            logger.info("已提交: %s", item["title"][:50])
            add_history("submit_ok", f"[{source_name}] {item['title'][:60]}")
    else:
        # 提交失败，加入重试队列
        for item in new_links:
            update_offline_task(item["task_id"], status="失败",
                                message=result.get("error", "提交失败"))
            _enqueue_retry(item["task_id"], retry_count=0)
            err_msg = result.get("error") or "未知错误"
            logger.warning("提交失败(%s), 加入重试队列: %s", err_msg, item["title"][:50])
            add_history("submit_fail", f"[{source_name}] {item['title'][:60]}: {err_msg}")

    return max_ep if result["ok"] else 0


def _enqueue_retry(task_id: int, retry_count: int = 0, max_retries: int = 5):
    """加入重试队列"""
    delay = min(2 ** retry_count * 5, 120)  # 指数退避，最多2小时
    retry_after = (datetime.now(timezone.utc) + timedelta(minutes=delay)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    add_retry(task_id, retry_after, retry_count, max_retries)
    update_offline_task(task_id, retry_count=retry_count)


def process_retry_queue():
    """处理重试队列"""
    tasks = get_retryable_tasks()
    if not tasks:
        return

    cfg = load_global()
    save_dir_id = cfg.get("save_dir_id", 0)

    for task in tasks:
        task_id = task["id"]
        # 使用 retry_queue 表中的计数（offline_tasks 表的 retry_count 可能不准确）
        retry_count = (task.get("retry_queue_count") or task.get("retry_count") or 0) + 1
        max_retries = task.get("max_retries", 5)

        if retry_count > max_retries:
            update_offline_task(task_id, status="失败",
                                message=f"重试{max_retries}次均失败")
            remove_retry(task_id)
            add_history("retry_giveup", f"[{task['source_name']}] {task['title'][:60]}")
            # 发送失败通知
            notify_failure(
                title=task["title"],
                source_name=task["source_name"],
                reason=f"重试{max_retries}次均失败",
                episode_num=task.get("episode_num", 0),
                season_num=task.get("season_num", 0),
                quality=task.get("quality", ""),
                image_url=task.get("image_url", ""),
                task_id=task_id,
            )
            continue

        logger.info("重试任务(%d/%d): %s", retry_count, max_retries, task["title"][:50])

        result = submit_urls([task["link"]], save_dir_id)
        if result["ok"]:
            # 提取 info_hash
            resp_data = result.get("data", {})
            ih = (resp_data.get("info_hash") or
                  resp_data.get("data", {}).get("info_hash") or "")
            if isinstance(ih, (list, tuple)):
                ih = ih[0] if ih else ""
            if not ih:
                ih = extract_info_hash(task["link"])
            update_offline_task(task_id, status="已提交",
                                info_hash=ih, message="重试成功")
            remove_retry(task_id)
            add_history("retry_ok", f"[{task['source_name']}] {task['title'][:60]}")
        else:
            update_offline_task(task_id, status="等待提交",
                                message=result.get("error", "重试失败"))
            _enqueue_retry(task_id, retry_count, max_retries)


def sync_offline_status():
    """同步 115 离线任务状态"""
    client = get_client()
    if not client:
        return

    logger.info("同步 115 离线任务状态...")
    conn = None
    try:
        conn = get_conn()
        # 获取本地待同步的任务（含标题、封面、清晰度等，用于通知）
        rows = conn.execute(
            """SELECT id, info_hash, title, source_name,
                      episode_num, season_num, quality, image_url
               FROM offline_tasks
               WHERE status IN ('已提交') AND info_hash != ''"""
        ).fetchall()

        if not rows:
            logger.debug("无待同步的离线任务")
            return

        # 构建 info_hash → 本地信息的映射
        local_map = {}
        for r in rows:
            local_map[r["info_hash"]] = {
                "id": r["id"],
                "title": r["title"],
                "source_name": r["source_name"],
                "episode_num": r["episode_num"] or 0,
                "season_num": r["season_num"] or 0,
                "quality": r["quality"] or "",
                "image_url": r["image_url"] or "",
            }
        logger.info("本地待同步 info_hash: %s", list(local_map.keys()))

        # 分页拉取 115 离线任务列表
        page = 1
        while True:
            try:
                resp = check_response(client.offline_list(page, method='POST'))
                data = resp.get("data", resp)
                tasks_115 = data.get("tasks", []) if isinstance(data, dict) else []
                if not tasks_115:
                    break
                for i, t in enumerate(tasks_115):
                    if page == 1 and i == 0:
                        logger.debug("115 任务样例: %s", {k: v for k, v in t.items() if k in ('info_hash', 'state', 'ih', 'status', 'task_id', 'task_name')})
                    # 兼容不同字段名
                    ih = t.get("info_hash") or t.get("ih") or ""
                    if not ih:
                        continue
                    if ih in local_map:
                        local_info = local_map.pop(ih)
                        task_id = local_info["id"]
                        # 兼容不同字段名
                        state = t.get("state") or t.get("status") or 0
                        if isinstance(state, str):
                            state = {"已完成": 2, "下载中": 1, "失败": 3}.get(state, 0)
                        if state == 2:  # 完成
                            update_offline_task(task_id, status="已完成",
                                                message="离线完成")
                            # 发送成功通知（含封面、清晰度等）
                            notify_success(
                                title=local_info["title"],
                                source_name=local_info["source_name"],
                                episode_num=local_info.get("episode_num", 0),
                                season_num=local_info.get("season_num", 0),
                                quality=local_info.get("quality", ""),
                                image_url=local_info.get("image_url", ""),
                                task_id=task_id,
                            )
                        elif state == 1:  # 离线中
                            update_offline_task(task_id, status="已提交",
                                                message="离线中")
                        elif state == 3:  # 失败
                            update_offline_task(task_id, status="失败",
                                                message="离线失败")
                            notify_failure(
                                title=local_info["title"],
                                source_name=local_info["source_name"],
                                reason="115 离线失败",
                                episode_num=local_info.get("episode_num", 0),
                                season_num=local_info.get("season_num", 0),
                                quality=local_info.get("quality", ""),
                                image_url=local_info.get("image_url", ""),
                                task_id=task_id,
                            )
                page += 1
                if len(tasks_115) < 20:
                    break
            except Exception as e:
                logger.warning("获取115离线任务列表第%d页失败: %s", page, e)
                break

        matched = len(rows) - len(local_map)  # rows 总数 - 未匹配的
        logger.info("同步完成: 已提交=%d, 匹配到=%d", len(rows), matched)
    except Exception as e:
        logger.error("同步离线状态失败: %s", e)
    finally:
        if conn:
            conn.close()


def do_vacuum():
    """定时数据清理"""
    cfg = load_global()
    days = cfg.get("history_keep_days", 60)
    db_vacuum(days)
    logger.info("数据清理完成（保留%d天）", days)
