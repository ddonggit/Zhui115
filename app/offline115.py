"""Zhui115 115 网盘离线下载封装

基于 p115client 库，提供磁力链/ED2K 提交、任务查询、配额查询等操作。
"""

import time
import re
import logging
import traceback
import errno
from typing import Optional

from p115client import P115Client, check_response, P115OSError

from .config import load_global, save_global

logger = logging.getLogger("zhui115.offline")

# 磁力链接净化正则：只保留 xt=urn:btih: 部分，去掉 &dn= &tr= 等一切多余参数
_MAGNET_CLEAN = re.compile(
    r'(magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40})'
)
# info_hash 提取正则（从磁力链接中）
_INFO_HASH_RE = re.compile(r'xt=urn:btih:([a-fA-F0-9]{32,40})')


def extract_info_hash(url: str) -> str:
    """从磁力链接中提取 info_hash"""
    if url.startswith("magnet:"):
        m = _INFO_HASH_RE.search(url)
        if m:
            return m.group(1).lower()
    return ""


def _clean_magnet(url: str) -> str:
    """将磁力链接精简为纯净格式，只保留 magnet:?xt=urn:btih:<hash>"""
    if url.startswith("magnet:"):
        m = _MAGNET_CLEAN.search(url)
        if m:
            cleaned = m.group(0)
            if cleaned != url:
                logger.debug("磁力链接已净化: %s... → %s", url[:60], cleaned)
            return cleaned
    return url


def get_client() -> Optional[P115Client]:
    """获取 P115Client 实例（从全局配置读取 cookie）"""
    cfg = load_global()
    cookie = cfg.get("cookie_115", "").strip()
    if not cookie:
        return None
    try:
        return P115Client(cookie, check_for_relogin=True)
    except Exception as e:
        logger.error("创建 P115Client 失败: %s", e)
        return None


def get_save_dir_id(client: P115Client) -> int:
    """获取或创建保存目录的 ID"""
    cfg = load_global()
    dir_id = cfg.get("save_dir_id", 0)
    dir_name = cfg.get("save_dir_name", "/追剧")

    if dir_id and dir_id != 0:
        return dir_id

    # 尝试按路径创建目录
    try:
        path = dir_name.strip("/")
        parts = path.split("/")
        current_id = 0
        for part in parts:
            if not part:
                continue
            current_id = _find_or_create_dir(client, current_id, part)
        # 保存 ID
        if current_id:
            cfg["save_dir_id"] = current_id
            save_global(cfg)
        return current_id
    except Exception as e:
        logger.warning("获取/创建保存目录失败: %s", e)
        return 0


def _find_or_create_dir(client: P115Client, parent_id: int, name: str) -> int:
    """在指定父目录下查找或创建子目录"""
    # 先尝试创建（如果已存在会返回错误，fallback 到查找）
    try:
        resp = check_response(
            client.fs_mkdir(name, pid=parent_id)
        )
        if isinstance(resp, dict):
            dir_id = resp.get("id")
            if dir_id:
                return int(dir_id)
    except Exception:
        pass

    # 遍历查找
    try:
        resp = check_response(
            client.fs_files({"cid": parent_id, "limit": 1000})
        )
        data = resp.get("data", [])
        if isinstance(data, dict):
            data = data.get("list", [])
        for item in data:
            if item.get("n") == name and item.get("icount") == 0:
                return int(item.get("aid") or item.get("cid") or 0)
    except Exception:
        pass

    return 0


def _is_duplicate_error(err_msg: str) -> bool:
    """检测 115 的"任务已存在"错误（errcode 10008 / errcode 20004）"""
    return ("10008" in err_msg and "任务已存在" in err_msg) or \
           ("20004" in err_msg and "已存在" in err_msg)


def submit_urls(urls: list[str], save_dir_id: int = 0) -> dict:
    """提交磁力/ED2K 链接到 115 离线下载

    返回:
        {"ok": True, "data": {...}} 或 {"ok": False, "error": "..."}
    """
    client = get_client()
    if not client:
        return {"ok": False, "error": "115 Cookie 未配置或无效"}

    if not save_dir_id:
        save_dir_id = get_save_dir_id(client)

    try:
        # 净化所有磁力链接
        cleaned = [_clean_magnet(u) for u in urls]
        logger.debug("待提交链接: %s", [u[:80] for u in cleaned])
        # 传入 url[0]=..., url[1]=... 格式（P115Client lixianssp 专用）
        payload = {f"url[{i}]": u for i, u in enumerate(cleaned)}
        if save_dir_id:
            payload["wp_path_id"] = save_dir_id

        resp = check_response(
            client.offline_add_urls(payload)
        )
        return {"ok": True, "data": resp}
    except P115OSError as e:
        # errno.EEXIST (17) = 任务已存在（对应115 errno 20004），视为成功
        if e.errno == errno.EEXIST:
            logger.info("任务已存在（errno=20004），视为提交成功")
            return {"ok": True, "data": getattr(e, 'args', [{}])[-1] or {}}
        # errno 5 (EIO) 时检查 errcode 10008：115 返回"任务已存在"，同样视为成功
        err_msg = str(e)
        if _is_duplicate_error(err_msg):
            logger.info("任务已存在（errcode=10008），视为提交成功：%s", err_msg[:120])
            return {"ok": True, "data": getattr(e, 'args', [{}])[-1] or {}}
        logger.error("提交离线下载失败: %s\n%s", e, traceback.format_exc())
        return {"ok": False, "error": str(e)}
    except Exception as e:
        err_msg = str(e)
        if _is_duplicate_error(err_msg):
            logger.info("任务已存在（errcode=10008），视为提交成功：%s", err_msg[:120])
            return {"ok": True, "data": {}}
        logger.error("提交离线下载失败: %s\n%s", e, traceback.format_exc())
        return {"ok": False, "error": str(e)}


def query_quota() -> dict:
    """查询 115 离线配额"""
    client = get_client()
    if not client:
        return {"ok": False, "error": "115 Cookie 未配置"}

    try:
        resp = check_response(client.offline_quota_info())
        return {"ok": True, "data": resp}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_offline(page: int = 1) -> dict:
    """获取 115 离线任务列表"""
    client = get_client()
    if not client:
        return {"ok": False, "error": "115 Cookie 未配置"}

    try:
        resp = check_response(client.offline_list(page))
        return {"ok": True, "data": resp}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def remove_task(info_hash: str) -> dict:
    """删除 115 离线任务"""
    client = get_client()
    if not client:
        return {"ok": False, "error": "115 Cookie 未配置"}

    try:
        resp = check_response(
            client.offline_remove({"info_hash": info_hash})
        )
        return {"ok": True, "data": resp}
    except Exception as e:
        return {"ok": False, "error": str(e)}
