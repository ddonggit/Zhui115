#!/usr/bin/env python3
"""Zhui115 — 自动追剧 RSS 监控 + 115 离线下载

基于 p115client 实现磁力链/ED2K 自动离线到 115 网盘。

用法:
  python3 main.py                    # 启动 Web + 调度
  python3 main.py --web-only         # 仅启动 Web
  python3 main.py --scheduler-only   # 仅启动调度
  python3 main.py --check-now        # 单次检查所有源
  python3 main.py --port 8300        # 指定端口
"""

import argparse
import logging
import os
import threading

from app.config import load_global
from app.scheduler import start as sched_start, stop as sched_stop, check_all_sources
from app.web.server import run as web_run


def setup_logging(level=logging.INFO):
    # 优先读取环境变量 ZHUI115_LOG_LEVEL
    env_lvl = os.environ.get("ZHUI115_LOG_LEVEL", "").strip().upper()
    if env_lvl:
        level = getattr(logging, env_lvl, level)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Zhui115 — 自动追剧 RSS 监控 + 115 离线下载"
    )
    parser.add_argument("--web-only", action="store_true", help="仅启动 Web")
    parser.add_argument("--scheduler-only", action="store_true", help="仅启动调度")
    parser.add_argument("--check-now", action="store_true", help="单次检查所有源")
    parser.add_argument("--port", type=int, default=0, help="Web 端口")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level)
    logger = logging.getLogger("zhui115")
    logger.debug("日志级别: DEBUG")

    cfg = load_global()
    port = args.port or cfg.get("web_port", 8300)

    if args.check_now:
        logger.info("单次检查所有 RSS 源...")
        check_all_sources()
        logger.info("检查完成")
        return

    if args.web_only:
        logger.info("仅启动 Web 服务（端口 %d）", port)
        web_run(port=port)
        return

    if args.scheduler_only:
        logger.info("仅启动定时调度")
        sched_start()
        try:
            # 保持进程运行
            event = threading.Event()
            event.wait()
        except KeyboardInterrupt:
            sched_stop()
        return

    # 默认：Web + 调度
    logger.info("🚀 Zhui115 启动 (Web端口 %d)", port)
    logger.info("Cookie 已配置: %s", "✅" if cfg.get("cookie_115") else "❌")

    sched_start()

    try:
        web_run(port=port)
    except KeyboardInterrupt:
        pass
    finally:
        sched_stop()
        logger.info("Zhui115 已停止")


if __name__ == "__main__":
    main()
