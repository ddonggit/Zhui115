"""Zhui115 RSS 抓取与解析模块

统一入口 parse_rss(url) -> list[dict]
每个条目: {title, link, link_hash, episode_num, season_num, image_url, quality}
支持标准 RSS 2.0 / Atom / 磁力链 / ED2K 链接提取
"""

import hashlib
import logging
import re
from typing import Optional

import cloudscraper

from .config import load_global

logger = logging.getLogger("zhui115.rss")

# 用户代理池，随机轮换降低被拦截概率
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
]


def _build_scraper() -> cloudscraper.CloudScraper:
    """构建一个带随机 UA 的 cloudscraper 实例"""
    import random
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "mobile": False,
        }
    )
    scraper.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    return scraper


def parse_rss(url: str) -> list[dict]:
    """抓取并解析 RSS 源，返回条目列表

    参数:
        url: RSS 订阅地址
    返回:
        list[dict]: 每个条目包含 title, link, link_hash, episode_num, season_num,
                    image_url, quality
    """
    import feedparser

    scraper = _build_scraper()
    try:
        resp = scraper.get(url, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("RSS 请求失败 [%s]: %s", url[:60], e)
        raise

    content = resp.content
    # 检查是否触发了 Cloudflare 挑战
    text_lower = content[:2000].lower()
    if b"just a moment" in content or b"cf-browser-verification" in content:
        logger.warning("Cloudflare 验证拦截: %s", url[:60])
        raise RuntimeError("Cloudflare 验证拦截")

    # 用 feedparser 解析
    try:
        feed = feedparser.parse(content)
    except Exception as e:
        logger.warning("RSS 解析失败 [%s]: %s", url[:60], e)
        raise

    items = []
    for entry in feed.entries:
        link = _extract_link(entry)
        if not link:
            continue

        title = entry.get("title", "").strip()
        if not title:
            continue

        # 生成链接指纹（用于去重）
        link_hash = hashlib.sha256(link.encode()).hexdigest()[:16]

        # 尝试从标题提取集数、季数和清晰度
        ep_num = _extract_episode(title)
        season_num = _extract_season(title)
        quality = _extract_quality(title)
        # 尝试从条目中提取封面图
        image_url = _extract_image(entry)

        items.append({
            "title": title,
            "link": link,
            "link_hash": link_hash,
            "episode_num": ep_num,
            "season_num": season_num,
            "image_url": image_url,
            "quality": quality,
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


def _extract_quality(title: str) -> str:
    """从标题中提取清晰度/编码信息"""
    patterns = [
        (r'(2160p|2160P|4K|4k)', '4K'),
        (r'(1080p|1080P)', '1080p'),
        (r'(720p|720P)', '720p'),
        (r'(480p|480P)', '480p'),
        (r'(HEVC|hevc|H[. ]?265|h[. ]?265|x265)', 'HEVC'),
        (r'(H[. ]?264|h[. ]?264|x264)', 'H264'),
        (r'(Hi10P|hi10p|10bit)', '10bit'),
        (r'(DV|Dolby Vision|dovi)', 'DV'),
        (r'(HDR|hdr)', 'HDR'),
    ]
    seen = set()
    parts = []
    for pat, label in patterns:
        m = re.search(pat, title)
        if m and label not in seen:
            seen.add(label)
            parts.append(label)
    return " · ".join(parts[:4])  # 最多取 4 个标签


def _extract_image(entry) -> str:
    """从 RSS 条目中提取封面图 URL"""
    # 1. 检查 links 字段中的图片链接
    for link in entry.get("links", []):
        href = link.get("href", "")
        type_ = link.get("type", "")
        if type_.startswith("image/") and href:
            return href

    # 2. 检查 enclosures 字段中的图片
    for enc in entry.get("enclosures", []):
        href = enc.get("href", "")
        type_ = enc.get("type", "")
        if type_.startswith("image/") and href:
            return href

    # 3. 从 content/summary/description 的 HTML 中提取 <img> 标签
    content_text = ""
    for c in entry.get("content", []):
        content_text += c.get("value", "")
    content_text += entry.get("summary", "")
    content_text += entry.get("description", "")

    img_match = re.search(r'<img[^>]+src="([^"]+)"', content_text)
    if img_match:
        url = img_match.group(1)
        logger.debug("RSS 条目中发现图片: %s", url[:80])
        return url

    return ""
