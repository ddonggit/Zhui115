"""Zhui115 RESTful API

所有 API 路径使用路径参数标识实体。
"""

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote

from ..config import (
    load_global, save_global, load_sources, save_sources,
    add_source, update_source, delete_source, find_source,
    GLOBAL_PATH, SOURCES_PATH, DATA_DIR, DEFAULT_GLOBAL,
)
from ..db import (
    list_offline_tasks, list_history, get_task_stats,
    export_db, import_db, vacuum as db_vacuum,
    get_conn, add_history,
)
from ..offline115 import get_client, query_quota, list_offline, submit_urls
from ..scheduler import check_all_sources, scheduler, reschedule_check
from ..rss import parse_rss as parse_rss_url


def route(method: str, path: str, body: bytes = b"", query: dict = None):
    """API 路由分发"""
    query = query or {}

    # ── 全局配置 ──
    if path == "/api/global" and method == "GET":
        cfg = load_global()
        # 隐藏 cookie 敏感信息
        cfg_public = {k: v for k, v in cfg.items()}
        if cfg_public.get("cookie_115"):
            cfg_public["cookie_115"] = cfg_public["cookie_115"][:20] + "..."
        return _ok(cfg_public)

    if path == "/api/global" and method == "PUT":
        data = _json(body)
        if data is None:
            return _err("无效的 JSON")
        cfg = load_global()
        # 允许更新的字段
        allowed = [
            "cookie_115", "save_dir_id", "save_dir_name",
            "check_interval", "retry_interval", "max_retries",
            "history_keep_days", "quota_warning", "web_port",
        ]
        for k in allowed:
            if k in data:
                cfg[k] = data[k]
        save_global(cfg)
        add_history("config_update", "更新全局配置")
        # 如果检查间隔变了，重新调度
        if "check_interval" in data:
            reschedule_check()
        return _ok(cfg)

    # ── Cookie 单独接口（完整读写） ──
    if path == "/api/cookie" and method == "GET":
        cfg = load_global()
        return _ok({"cookie_115": cfg.get("cookie_115", "")})

    if path == "/api/cookie" and method == "PUT":
        data = _json(body)
        if data is None or "cookie_115" not in data:
            return _err("缺少 cookie_115 字段")
        cfg = load_global()
        cfg["cookie_115"] = data["cookie_115"]
        save_global(cfg)
        add_history("cookie_update", "更新 115 Cookie")
        return _ok({"message": "Cookie 已更新"})

    # ── RSS 源管理 ──
    if path == "/api/sources" and method == "GET":
        srcs = load_sources()
        return _ok(srcs)

    if path == "/api/sources" and method == "POST":
        data = _json(body)
        if data is None or not data.get("name") or not data.get("url"):
            return _err("缺少 name 或 url")
        if find_source(data["name"]):
            return _err(f"源 '{data['name']}' 已存在")
        source = {
            "name": data["name"],
            "url": data["url"],
            "enabled": data.get("enabled", True),
            "show_name": data.get("show_name", ""),
            "season": data.get("season", 0),
            "filter_keywords": data.get("filter_keywords", []),
            "filter_exclude": data.get("filter_exclude", []),
            "episode_pattern": data.get("episode_pattern", ""),
            "auto_episode": data.get("auto_episode", False),
            "last_episode": data.get("last_episode", 0),
            "episode_from": data.get("episode_from", 0),
            "episode_to": data.get("episode_to", 0),
            "regex_filter": data.get("regex_filter", False),
            "check_interval": data.get("check_interval", 0),
            "dedup_group": data.get("dedup_group", ""),
            "description": data.get("description", ""),
        }
        if add_source(source):
            add_history("source_add", f"添加源: {source['name']}")
            return _ok(source, 201)
        return _err("添加失败")

    # 单个源的操作 /api/sources/{name}
    if path.startswith("/api/sources/") and method == "GET":
        name = _parse_name(path)
        src = find_source(name)
        if not src:
            return _err("源不存在", 404)
        return _ok(src)

    if path.startswith("/api/sources/") and method == "PUT":
        name = _parse_name(path)
        data = _json(body)
        if data is None:
            return _err("无效的 JSON")
        if update_source(name, data):
            add_history("source_update", f"更新源: {name}")
            return _ok({"message": "已更新"})
        return _err("更新失败或源不存在", 404)

    if path.startswith("/api/sources/") and method == "DELETE":
        name = _parse_name(path)
        if delete_source(name):
            add_history("source_delete", f"删除源: {name}")
            return _ok({"message": "已删除"})
        return _err("源不存在", 404)

    if path == "/api/sources/test" and method == "POST":
        """测试 RSS 源"""
        data = _json(body)
        if data is None or not data.get("url"):
            return _err("缺少 url")
        try:
            items = parse_rss_url(data["url"])
            return _ok({
                "total": len(items),
                "items": items[:10],  # 只返回前10条
            })
        except Exception as e:
            return _err(f"解析失败: {e}")

    # ── 离线任务 ──
    if path == "/api/tasks" and method == "GET":
        page = int(query.get("page", 1))
        page_size = int(query.get("page_size", 20))
        status = query.get("status", "")
        source = query.get("source", "")
        return _ok(list_offline_tasks(page, page_size, status or None, source or None))

    if path == "/api/tasks/stats" and method == "GET":
        return _ok(get_task_stats())

    # ── 重试队列 ──
    if path == "/api/retry" and method == "GET":
        from app.db import get_conn
        conn = get_conn()
        try:
            rows = conn.execute(
                """SELECT t.*, r.retry_after, r.retry_count as r_count, r.max_retries
                   FROM offline_tasks t
                   INNER JOIN retry_queue r ON r.task_id = t.id
                   ORDER BY r.retry_after"""
            ).fetchall()
            return _ok([dict(r) for r in rows])
        finally:
            conn.close()

    # ── 历史 ──
    if path == "/api/history" and method == "GET":
        page = int(query.get("page", 1))
        page_size = int(query.get("page_size", 50))
        return _ok(list_history(page, page_size))

    # ── 115 状态 ──
    if path == "/api/115/status" and method == "GET":
        client = get_client()
        if not client:
            return _ok({"connected": False, "message": "未配置 Cookie"})
        try:
            quota = query_quota()
            return _ok({
                "connected": True,
                "quota": quota,
            })
        except Exception as e:
            return _ok({"connected": False, "message": str(e)})

    if path == "/api/115/offline-list" and method == "GET":
        page = int(query.get("page", 1))
        return _ok(list_offline(page))

    # ── 调度控制 ──
    if path == "/api/scheduler/status" and method == "GET":
        jobs = []
        if scheduler and scheduler.running:
            for j in scheduler.get_jobs():
                jobs.append({
                    "id": j.id,
                    "name": j.name,
                    "next_run": str(j.next_run_time) if j.next_run_time else None,
                })
        return _ok({
            "running": scheduler.running if scheduler else False,
            "jobs": jobs,
        })

    if path == "/api/scheduler/run-now" and method == "POST":
        check_all_sources()
        return _ok({"message": "已触发检查"})

    # ── 数据操作 ──
    if path == "/api/data/backup" and method == "GET":
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"zhui115_backup_{ts}.db"
        if export_db(str(backup_path)):
            # 同时备份配置文件
            shutil.copy(GLOBAL_PATH, backup_dir / f"global_{ts}.json")
            shutil.copy(SOURCES_PATH, backup_dir / f"sources_{ts}.json")
            add_history("backup", f"备份到 {backup_path.name}")
            # 直接返回文件供用户下载
            file_data = backup_path.read_bytes()
            filename = backup_path.name
            return (
                200, file_data, "application/octet-stream",
                {"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        return _err("备份失败")

    if path == "/api/data/backups" and method == "GET":
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(backup_dir.glob("*.db"), key=os.path.getmtime, reverse=True)
        return _ok([
            {"name": f.name, "size": f.stat().st_size,
             "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()}
            for f in files
        ])

    if path == "/api/data/restore" and method == "POST":
        data = _json(body)
        if data is None or not data.get("name"):
            return _err("缺少 name (备份文件名)")
        backup_dir = DATA_DIR / "backups"
        restore_path = backup_dir / data["name"]
        if not restore_path.exists():
            return _err(f"备份文件不存在: {restore_path.name}", 404)
        if import_db(str(restore_path)):
            # 恢复配置文件
            base = restore_path.stem.replace("zhui115_backup_", "")
            global_bak = backup_dir / f"global_{base}.json"
            sources_bak = backup_dir / f"sources_{base}.json"
            if global_bak.exists():
                shutil.copy(str(global_bak), GLOBAL_PATH)
            if sources_bak.exists():
                shutil.copy(str(sources_bak), SOURCES_PATH)
            add_history("restore", f"从 {restore_path.name} 恢复")
            return _ok({"message": "恢复成功"})
        return _err("恢复失败")

    if path == "/api/data/vacuum" and method == "POST":
        data = _json(body) or {}
        days = data.get("keep_days", 60)
        try:
            db_vacuum(days)
            return _ok({"message": f"清理完成，保留{days}天"})
        except Exception as e:
            return _err(str(e))

    return _err("未找到路由", 404)


def _json(body: bytes):
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _parse_name(path: str) -> str:
    """从 /api/sources/{name} 中提取 name（URL 解码）"""
    parts = path.split("/")
    if len(parts) >= 4:
        return unquote(parts[3])
    return ""


def _ok(data, status=200):
    return status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json"


def _err(msg, status=400):
    return status, json.dumps({"error": msg}, ensure_ascii=False).encode("utf-8"), "application/json"
