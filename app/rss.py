"""Zhui115 RSS 抓取与解析模块

统一入口 parse_rss(url) -> list[dict]
每个条目: {title, link, link_hash, episode_num, season_num}
支持标准 RSS 2.0 / Atom / 磁力链 / ED2K 链接提取

防触发 Cloudflare 措施：
  - 随机 User-Agent
  - 检测 CF 挑战页 / 非 RSS 响应
  - 源级限频检查（外部调用者负责间隔）
"""

import hashlib
import logging
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, parse_qs

import feedparser

logger = logging.getLogger("zhui115.rss")

# 优先使用 cloudscraper（绕过 Cloudflare），否则回落 requests
try:
    import cloudscraper
    _session = cloudscraper.create_scraper()
    logger.info("使用 cloudscraper（已启用 Cloudflare 绕过）")
except ImportError:
    import requests
    _session = requests.Session()
    logger.info("使用 requests（未安装 cloudscraper）")

# 模拟真实浏览器的 User-Agent 池（轮换使用，降低被识别概率）
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


def _random_headers() -> dict:
    """生成带随机 UA 的请求头"""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def _is_cloudflare_challenge(content: bytes) -> bool:
    """检测响应是否为 Cloudflare 挑战页"""
    text = content[:2000].lower()
    signals = [b"just a moment", b"checking your browser",
               b"cf-browser-verification", b"cf_chl_opt",
               b"challenge-platform", b"__cf_chl_f_tk"]
    return any(s in text for s in signals)


def _looks_like_rss(content: bytes) -> bool:
    """粗略判断内容是否为 RSS / Atom XML"""
    text = content[:500].lower()
    return any(s in text for s in [b"<rss", b"<feed", b"<channel>",
                                    b"<item>", b"<entry>"])


def parse_rss(url: str, timeout: int = 60) -> list[dict]:
    """抓取并解析 RSS 源，返回条目列表

    自动检测 Cloudflare 挑战页并抛出明确错误。
    """
    try:
        resp = _session.get(url, timeout=timeout, headers=_random_headers())
        resp.raise_for_status()
        content = resp.content
    except Exception as e:
        raise RuntimeError(f"获取 RSS 失败: {e}")

    # 检测 Cloudflare 挑战
    if _is_cloudflare_challenge(content):
        raise RuntimeError("触发了 Cloudflare 挑战，已被拦截")

    # 检测是否真的是 RSS XML
    if not _looks_like_rss(content):
        # 可能是 404 页面或非 XML 错误页
        snippet = content[:200].decode("utf-8", errors="replace")
        logger.warning("响应不是 RSS XML: %s ...", snippet)
        raise RuntimeError("返回内容不是有效 RSS，可能是被拦截或错误页面")

    feed = feedparser.parse(content)
    items = []

    for entry in feed.entries:
        title = entry.get("title", "").strip()
        if not title:
            continue

        # 提取链接：优先磁力/ED2K
        link = _extract_link(entry)
        if not link:
            continue

        logger.debug("提取到链接 [%s]: %s", title[:40], link[:120])

        link_hash = hashlib.sha256(link.encode()).hexdigest()[:16]

        # 尝试从标题提取集数和季数
        ep_num = _extract_episode(title)
        season_num = _extract_season(title)

        items.append({
            "title": title,
            "link": link,
            "link_hash": link_hash,
            "episode_num": ep_num,
            "season_num": season_num,
        })

    return items


def _extract_link(entry) -> Optional[str]:
    """从 RSS 条目中提取磁力/ED2K 链接"""

    # 1. 优先检查 links 字段
    for link in entry.get("links", []):
        href = link.get("href", "")
        if href.startswith("magnet:") or href.startswith("ed2k:"):
            return href

    # 2. 检查 enclosures
    for enc in entry.get("enclosures", []):
        href = enc.get("href", "")
        if href:
            return href

    # 3. 检查 content 中的链接（用正则）
    content_text = ""
    for c in entry.get("content", []):
        content_text += c.get("value", "")
    content_text += entry.get("summary", "")
    content_text += entry.get("description", "")

    # 从 HTML 内容中提取磁力链接
    mag_match = re.search(r'(magnet:\?[^\s"\'<>&]+)', content_text)
    if mag_match:
        return mag_match.group(1)

    ed2k_match = re.search(r'(ed2k://[^\s"\'<>&\|]+)', content_text)
    if ed2k_match:
        return ed2k_match.group(1)

    # 4. 退回到 link 字段
    link_val = entry.get("link", "")
    if link_val and (link_val.startswith("magnet:") or link_val.startswith("ed2k:")):
        return link_val

    return None


def _extract_episode(title: str) -> int:
    """从标题中提取集数"""
    patterns = [
        r'[第]?(\d{1,4})\s*[集話话話巻]',          # 第12集 / 12集
        r'[\[|【](\d{1,4})\s*[vV]?\s*[\]|】]',     # [12] / [12v2]
        r'[\[|【]0*(\d{1,4})\s*[Ee][Pp]?\s*[\]|】]', # [EP12] / [12]
        r'[Ee][Pp]\.?\s*0*(\d{1,4})',               # EP.12
        r'-?\s*0*(\d{1,4})\s*[vV]\d',               # 12v2
        r'Episode\s+0*(\d{1,4})',                    # Episode 12
    ]
    for pat in patterns:
        m = re.search(pat, title)
        if m:
            return int(m.group(1))
    return 0


def _extract_season(title: str) -> int:
    """从标题中提取季数"""
    patterns = [
        r'[第]([一二三四五六七八九十\d]+)\s*[季期]',  # 第二季 / 第2季
        r'[Ss]eason\s*(\d{1,2})',                   # Season 2
        r'[Ss](\d{1,2})\s*[Ee]',                    # S02E12
        r'第(\d+)\s*[季期]',                          # 第2季
    ]
    for pat in patterns:
        m = re.search(pat, title)
        if m:
            txt = m.group(1)
            # 处理中文数字
            cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                      "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
            if txt in cn_map:
                return cn_map[txt]
            try:
                return int(txt)
            except ValueError:
                pass
    return 0
