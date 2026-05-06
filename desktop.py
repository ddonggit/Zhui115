"""Zhui115 Windows 桌面版 — 入口

基于 PyQt6 + QWebEngineView，将 Web 管理界面嵌入原生窗口。
支持系统托盘、最小化到托盘、后台运行。

打包命令:
    pyinstaller --onefile --windowed --name Zhui115 --add-data "app/static;app/static" --hidden-import app.config --hidden-import app.scheduler --hidden-import app.db --hidden-import app.notifier --hidden-import app.rss --hidden-import app.offline115 --hidden-import web.server --hidden-import web.api --hidden-import apscheduler.triggers.interval --hidden-import apscheduler.triggers.cron --hidden-import cloudscraper --icon icon.ico desktop.py
"""

import logging
import os
import sys
import threading

# ── 确保 PyInstaller 收集所有需要的模块 ──
# 全部放在文件顶部，避免 PyInstaller 漏掉
import app.config
import app.db
import app.rss
import app.offline115
import app.notifier
import app.scheduler
import web.server
import web.api

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QSystemTrayIcon, QMenu,
    QMessageBox, QLabel,
)
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWebEngineWidgets import QWebEngineView

# ── 项目根目录 ──
_ROOT = os.path.dirname(os.path.abspath(__file__))
_MEIPASS = getattr(sys, '_MEIPASS', _ROOT)
if _MEIPASS not in sys.path:
    sys.path.insert(0, _MEIPASS)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── 配置日志（写入文件，不弹控制台窗口） ──
log_dir = os.path.join(_ROOT, "data")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    filename=os.path.join(log_dir, "zhui115.log"),
    filemode="a",
)
logger = logging.getLogger("zhui115.desktop")


def start_server() -> int:
    """在单独线程中启动 Web 服务，返回实际端口号"""
    cfg = app.config.load_config()
    port = cfg.get("web_port", 8300)

    server = web.server.create_server(port)
    actual_port = server.server_address[1]
    logger.info("Web 服务已启动: http://127.0.0.1:%d", actual_port)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return actual_port


def start_scheduler_if_needed():
    """启动调度器（非阻塞）"""
    try:
        app.scheduler.start()
        logger.info("调度器已启动")
    except Exception as e:
        logger.warning("调度器启动失败: %s", e)


# ═══════════════════════════════════════════════
#  PyQt6 桌面窗口
# ═══════════════════════════════════════════════

def run_desktop():
    """启动桌面窗口"""
    # ── 启动后端服务 ──
    try:
        port = start_server()
    except Exception as e:
        logger.exception("Web 服务启动失败")
        app = QApplication(sys.argv if hasattr(sys, 'frozen') else [])
        QMessageBox.critical(None, "启动失败", f"Web 服务启动失败:\n{e}")
        sys.exit(1)

    start_scheduler_if_needed()

    # ── 创建 Qt 应用 ──
    qt_app = QApplication(sys.argv if hasattr(sys, 'frozen') else [])
    qt_app.setApplicationName("Zhui115")
    qt_app.setQuitOnLastWindowClosed(False)

    # ── 主窗口 ──
    window = QMainWindow()
    window.setWindowTitle(f"Zhui115 — 自动追剧 (http://127.0.0.1:{port})")
    window.resize(1280, 800)
    window.setMinimumSize(900, 600)

    icon_path = os.path.join(_ROOT, "icon.png")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        window.setWindowIcon(app_icon)
    else:
        app_icon = None

    # ── 内嵌浏览器 ──
    browser = QWebEngineView()
    browser.setUrl(QUrl(f"http://127.0.0.1:{port}"))
    window.setCentralWidget(browser)

    # ── 加载提示覆盖 ──
    loading_label = QLabel("正在加载 Zhui115…", window)
    loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    loading_label.setStyleSheet("""
        QLabel {
            background-color: #0f1117;
            color: #e4e6ed;
            font-size: 18px;
            font-weight: 600;
        }
    """)
    loading_label.setGeometry(0, 0, 1280, 800)
    loading_label.raise_()
    browser.loadFinished.connect(lambda: loading_label.hide())

    # ── 系统托盘 ──
    tray_icon = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray_icon = QSystemTrayIcon()
        if app_icon:
            tray_icon.setIcon(app_icon)
        else:
            pix = qt_app.style().standardIcon(
                qt_app.style().StandardPixmap.SP_ComputerIcon
            )
            tray_icon.setIcon(pix)

        tray_icon.setToolTip("Zhui115 — 自动追剧")
        tray_menu = QMenu()
        show_action = QAction("显示窗口", qt_app)
        show_action.triggered.connect(lambda: (window.show(), window.activateWindow()))
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        quit_action = QAction("退出", qt_app)
        quit_action.triggered.connect(qt_app.quit)
        tray_menu.addAction(quit_action)
        tray_icon.setContextMenu(tray_menu)
        tray_icon.activated.connect(
            lambda reason: (
                window.show(), window.activateWindow()
            ) if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        tray_icon.show()

    # ── 窗口关闭事件 → 隐藏到托盘 ──
    def close_event(event):
        if tray_icon and tray_icon.isVisible():
            event.ignore()
            window.hide()
            tray_icon.showMessage(
                "Zhui115",
                "已最小化到托盘，双击图标恢复窗口",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        else:
            event.accept()

    window.closeEvent = close_event
    window.show()

    # ── 退出清理 ──
    def cleanup():
        logger.info("正在关闭…")
        try:
            app.scheduler.stop()
        except Exception:
            pass

    qt_app.aboutToQuit.connect(cleanup)
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    run_desktop()
