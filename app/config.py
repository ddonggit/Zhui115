"""Zhui115 配置管理"""

import json
import threading
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SOURCES_PATH = DATA_DIR / "sources.json"
GLOBAL_PATH = DATA_DIR / "global.json"
DB_PATH = DATA_DIR / "zhui115.db"

_lock = threading.Lock()

# ── 默认全局配置 ──
DEFAULT_GLOBAL = {
    "cookie_115": "",
    "save_dir_id": 0,          # 115 保存目录 ID（0=根目录）
    "save_dir_name": "/追剧",  # 保存目录名
    "check_interval": 30,      # RSS 检查间隔（分钟）
    "retry_interval": 10,      # 失败重试间隔（分钟）
    "max_retries": 5,          # 最大重试次数
    "history_keep_days": 60,   # 历史记录保留天数
    "quota_warning": 10,       # 剩余配额低于此值时告警
    "web_port": 8300,          # Web 端口
}

# ── 默认 RSS 源 ──
DEFAULT_SOURCES = [
    {
        "name": "动漫花园-动画",
        "url": "https://share.dmhy.org/topics/rss/sort_id/2/rss.xml",
        "enabled": True,
        "show_name": "",
        "season": 0,
        "filter_keywords": [],
        "filter_exclude": [],
        "episode_pattern": "",
        "auto_episode": False,
        "last_episode": 0,
        "episode_from": 0,      # 起始集数（0=不限）
        "episode_to": 0,        # 结束集数（0=不限）
        "regex_filter": False,  # 过滤关键词是否启用正则
        "check_interval": 0,
        "dedup_group": "",
        "description": "动漫花园 动画分类",
    },
]

# ── 默认源字段定义（防手误） ──
_SOURCE_FIELDS = [
    "name", "url", "enabled", "show_name", "season",
    "filter_keywords", "filter_exclude", "episode_pattern",
    "auto_episode", "last_episode", "episode_from", "episode_to",
    "regex_filter",
    "check_interval", "dedup_group", "description",
]


def load_json(path: Path, default):
    """读取 JSON 文件，不存在则写入默认值"""
    if not path.exists():
        save_json(path, default)
        return default
    try:
        with _lock, open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data) -> bool:
    """写入 JSON 文件"""
    try:
        with _lock, open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


# ── 全局配置 ──

def load_global() -> dict:
    cfg = load_json(GLOBAL_PATH, DEFAULT_GLOBAL)
    # 补缺失字段
    changed = False
    for k, v in DEFAULT_GLOBAL.items():
        if k not in cfg:
            cfg[k] = v
            changed = True
    if changed:
        save_global(cfg)
    return cfg


def save_global(cfg: dict) -> bool:
    return save_json(GLOBAL_PATH, cfg)


# ── RSS 源管理 ──

def load_sources() -> list[dict]:
    srcs = load_json(SOURCES_PATH, DEFAULT_SOURCES)
    # 补缺失字段
    changed = False
    fields = _SOURCE_FIELDS
    for src in srcs:
        for f in fields:
            if f not in src:
                src[f] = "" if f != "enabled" else True
                if f in ("filter_keywords", "filter_exclude"):
                    src[f] = []
                elif f in ("season", "last_episode", "episode_from", "episode_to", "check_interval"):
                    src[f] = 0
                elif f == "regex_filter":
                    src[f] = False
                changed = True
    if changed:
        save_sources(srcs)
    return srcs


def save_sources(srcs: list[dict]) -> bool:
    return save_json(SOURCES_PATH, srcs)


def find_source(name: str) -> Optional[dict]:
    for s in load_sources():
        if s["name"] == name:
            return s
    return None


def add_source(source: dict) -> bool:
    srcs = load_sources()
    if any(s["name"] == source.get("name") for s in srcs):
        return False
    srcs.append(source)
    return save_sources(srcs)


def update_source(name: str, updates: dict) -> bool:
    srcs = load_sources()
    for s in srcs:
        if s["name"] == name:
            for k, v in updates.items():
                if k in _SOURCE_FIELDS:
                    s[k] = v
            return save_sources(srcs)
    return False


def delete_source(name: str) -> bool:
    srcs = load_sources()
    before = len(srcs)
    srcs = [s for s in srcs if s["name"] != name]
    if len(srcs) == before:
        return False
    return save_sources(srcs)
