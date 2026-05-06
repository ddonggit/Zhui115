"""Zhui115 通知模块

支持通过 Telegram Bot API 发送精美通知消息。
优先使用 RSS 自带封面图，无图时通过 TMDB API 按标题搜索补完。
"""

import re
import logging
from typing import Optional

import requests

from .config import load_global
from .db import update_offline_task

logger = logging.getLogger("zhui115.notifier")

TELEGRAM_API = "https://api.telegram.org/bot{token}"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
_TELEGRAM_TIMEOUT = 20
_TMDB_TIMEOUT = 10


# ═══════════════════════════════════════════════
#  Telegram API 调用
# ═══════════════════════════════════════════════

def _call(method: str, token: str, payload: dict, files: dict = None) -> dict:
    """通用 Telegram API 调用"""
    url = f"{TELEGRAM_API.format(token=token)}/{method}"
    try:
        if files:
            resp = requests.post(url, data=payload, files=files, timeout=_TELEGRAM_TIMEOUT)
        else:
            resp = requests.post(url, json=payload, timeout=_TELEGRAM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            return {"ok": True, "data": data}
        return {"ok": False, "error": data.get("description", "Telegram 返回未知错误")}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"请求失败: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _get_config():
    """获取通知配置"""
    cfg = load_global()
    return (
        cfg.get("telegram_bot_token", "").strip(),
        cfg.get("telegram_chat_id", "").strip(),
    )


def _is_enabled(event_key: str) -> bool:
    """检查某个通知类型是否开启"""
    cfg = load_global()
    return bool(cfg.get(event_key, True))


# ═══════════════════════════════════════════════
#  消息构建
# ═══════════════════════════════════════════════

def _build_subtitle(season_num: int = 0, episode_num: int = 0, quality: str = "") -> str:
    """构建副标题行：第N季 · 第M集 · 清晰度"""
    parts = []
    if season_num:
        parts.append(f"第{season_num}季")
    if episode_num:
        parts.append(f"第{episode_num}集")
    if quality:
        parts.append(quality)
    return " · ".join(parts)


def _send_text(token: str, chat_id: str, text: str) -> dict:
    """发送纯文本消息"""
    return _call("sendMessage", token, {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })


def _send_photo(token: str, chat_id: str, image_url: str, caption: str) -> dict:
    """发送带图片的消息（图片 URL 方式）"""
    return _call("sendPhoto", token, {
        "chat_id": chat_id,
        "photo": image_url,
        "caption": caption,
        "parse_mode": "HTML",
    })


def _build_success_msg(title: str, episode_num: int = 0,
                       season_num: int = 0, quality: str = "") -> str:
    """构建离线成功消息文本"""
    subtitle = _build_subtitle(season_num, episode_num, quality)
    if subtitle:
        return f"🎬 <b>{title}</b>\n{subtitle}"
    return f"🎬 <b>{title}</b>"


def _build_failure_msg(title: str, reason: str, episode_num: int = 0,
                       season_num: int = 0, quality: str = "") -> str:
    """构建离线失败消息文本"""
    subtitle = _build_subtitle(season_num, episode_num, quality)
    lines = [f"🎬 <b>{title}</b>"]
    if subtitle:
        lines.append(subtitle)
    lines.append(f"❌ {reason}")
    return "\n".join(lines)


def _build_rss_failure_msg(source_name: str, reason: str) -> str:
    """构建 RSS 源失效消息文本"""
    return f"⚠️ <b>{source_name}</b>\n{reason}"


# ═══════════════════════════════════════════════
#  TMDB 封面图搜索（备用）
# ═══════════════════════════════════════════════

def _clean_title_for_search(title: str) -> str:
    """清理 RSS 标题，提取纯净的影视名称用于搜索

    去掉字幕组标记、集数信息、编码信息等修饰文字
    """
    # 1. 去掉【】和 [] 内的内容（字幕组名、技术标签）
    cleaned = re.sub(r'[【\[][^】\]]*[】\]]', '', title)
    # 2. 去掉末尾的集数标记：第12集 / 12 / - 12 等
    cleaned = re.sub(r'\s*[第]?(\d{1,4})\s*[集話话]\s*.*$', '', cleaned)
    cleaned = re.sub(r'\s*[-–—]\s*\d{1,4}\s*$', '', cleaned)
    # 3. 去掉清晰度/编码标签
    cleaned = re.sub(r'\s*(2160p|1080p|720p|480p|HEVC|H\.?264|x264|AAC|FLAC|CHT|CHS|BIG5|GB)', '', cleaned, flags=re.IGNORECASE)
    # 4. 去掉末尾的脏后缀
    cleaned = re.sub(r'[\s\-–—　]+$', '', cleaned)
    return cleaned.strip()


def _search_tmdb_poster(clean_title: str, season_num: int, api_key: str) -> str:
    """通过 TMDB API 搜索电视剧/电影的封面图 URL

    返回完整的 TMDB 图片 URL，未找到则返回空字符串
    """
    if not api_key or not clean_title:
        return ""

    # 优先搜 TV（番剧通常是 TV 类型）
    medias = [
        ("tv", "电视剧"),
        ("movie", "电影"),
    ]
    for media_type, label in medias:
        try:
            url = f"https://api.themoviedb.org/3/search/{media_type}"
            resp = requests.get(url, params={
                "api_key": api_key,
                "query": clean_title,
                "language": "zh-CN",
                "page": 1,
            }, timeout=_TMDB_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            if results:
                poster = results[0].get("poster_path")
                if poster:
                    logger.debug("TMDB %s 找到封面: id=%s title=%s",
                                 label, results[0].get("id"),
                                 results[0].get("name", clean_title)[:30])
                    return f"{TMDB_IMAGE_BASE}{poster}"
        except requests.exceptions.RequestException as e:
            logger.debug("TMDB %s 搜索失败 [%s]: %s", label, clean_title[:30], e)
            continue

    return ""


def _resolve_image(title: str, image_url: str,
                   episode_num: int, season_num: int,
                   task_id: Optional[int] = None) -> str:
    """解析最终使用的封面图 URL

    优先级: RSS 自带图 > TMDB 搜索 > 无图
    """
    # 已有图直接用
    if image_url:
        return image_url

    # 尝试 TMDB 搜索
    cfg = load_global()
    api_key = cfg.get("tmdb_api_key", "").strip()
    if not api_key:
        return ""

    clean_title = _clean_title_for_search(title)
    if not clean_title:
        return ""

    found_url = _search_tmdb_poster(clean_title, season_num, api_key)
    if found_url and task_id:
        # 缓存到数据库，下次直接使用
        try:
            update_offline_task(task_id, image_url=found_url)
            logger.debug("TMDB 封面已缓存到 task_id=%s", task_id)
        except Exception as e:
            logger.warning("TMDB 封面缓存失败: %s", e)

    return found_url


# ═══════════════════════════════════════════════
#  公开通知函数
# ═══════════════════════════════════════════════

def notify_success(title: str, source_name: str,
                   episode_num: int = 0, season_num: int = 0,
                   quality: str = "", image_url: str = "",
                   task_id: int = 0) -> bool:
    """任务离线成功通知"""
    if not _is_enabled("notify_on_success"):
        return False
    token, chat_id = _get_config()
    if not token or not chat_id:
        return False

    msg = _build_success_msg(title, episode_num, season_num, quality)
    logger.info("推送成功通知: %s", title[:40])

    # 尝试获取封面图（RSS 自带 → TMDB 备用）
    img_url = _resolve_image(title, image_url, episode_num, season_num,
                             task_id=task_id if task_id else None)

    if img_url:
        logger.debug("图片模式: %s", img_url[:80])
        result = _send_photo(token, chat_id, img_url, msg)
    else:
        logger.debug("纯文本模式（无封面图）")
        result = _send_text(token, chat_id, msg)

    if not result["ok"]:
        logger.warning("成功通知发送失败: %s", result.get("error"))
    return result["ok"]


def notify_failure(title: str, source_name: str, reason: str,
                   episode_num: int = 0, season_num: int = 0,
                   quality: str = "", image_url: str = "",
                   task_id: int = 0) -> bool:
    """任务离线失败通知"""
    if not _is_enabled("notify_on_failure"):
        return False
    token, chat_id = _get_config()
    if not token or not chat_id:
        return False

    msg = _build_failure_msg(title, reason, episode_num, season_num, quality)
    logger.info("推送失败通知: %s", title[:40])

    img_url = _resolve_image(title, image_url, episode_num, season_num,
                             task_id=task_id if task_id else None)

    if img_url:
        logger.debug("图片模式: %s", img_url[:80])
        result = _send_photo(token, chat_id, img_url, msg)
    else:
        logger.debug("纯文本模式（无封面图）")
        result = _send_text(token, chat_id, msg)

    if not result["ok"]:
        logger.warning("失败通知发送失败: %s", result.get("error"))
    return result["ok"]


def notify_rss_failure(source_name: str, reason: str) -> bool:
    """RSS 源失效通知"""
    if not _is_enabled("notify_on_rss_failure"):
        return False
    token, chat_id = _get_config()
    if not token or not chat_id:
        return False

    msg = _build_rss_failure_msg(source_name, reason)
    logger.info("推送 RSS 失效通知: %s", source_name)

    result = _send_text(token, chat_id, msg)
    if not result["ok"]:
        logger.warning("RSS 失效通知发送失败: %s", result.get("error"))
    return result["ok"]


def notify_test(token: str, chat_id: str) -> dict:
    """发送测试通知"""
    msg = "🔔 <b>Zhui115</b>\n通知配置正确 ✅"
    return _send_text(token.strip(), chat_id.strip(), msg)
