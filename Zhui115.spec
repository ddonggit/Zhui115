# -*- mode: python ; coding: utf-8 -*-
"""Zhui115 PyInstaller 打包配置

用法:
    pip install pyinstaller PyQt6 PyQt6-WebEngine
    pyinstaller Zhui115.spec
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent

a = Analysis(
    ['desktop.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # 前端静态文件（路径: app/static/, server.py 中 STATIC_DIR 匹配）
        (str(ROOT / 'app/static/index.html'), 'app/static'),
        (str(ROOT / 'app/static/style.css'), 'app/static'),
        (str(ROOT / 'app/static/app.js'), 'app/static'),
        (str(ROOT / 'app/__init__.py'), 'app'),
        (str(ROOT / 'app/config.py'), 'app'),
        (str(ROOT / 'app/db.py'), 'app'),
        (str(ROOT / 'app/rss.py'), 'app'),
        (str(ROOT / 'app/offline115.py'), 'app'),
        (str(ROOT / 'app/scheduler.py'), 'app'),
        (str(ROOT / 'app/notifier.py'), 'app'),
        (str(ROOT / 'app/web/__init__.py'), 'app/web'),
        (str(ROOT / 'app/web/api.py'), 'app/web'),
        (str(ROOT / 'app/web/server.py'), 'app/web'),
        # 图标（打包进 exe，运行时 desktop.py 可通过 _MEIPASS 读取）
        (str(ROOT / 'icon.ico'), '.'),
        (str(ROOT / 'icon.png'), '.'),
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'app.web.server',
        'app.web.api',
        'apscheduler.triggers.interval',
        'apscheduler.triggers.cron',
        'cloudscraper',
        'p115client',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'PIL',
        'pandas',
        'scipy',
        'setuptools',
        'pip',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Zhui115',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'icon.ico') if (ROOT / 'icon.ico').exists() else None,
)
