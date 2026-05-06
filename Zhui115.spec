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
        # 前端静态文件
        (str(ROOT / 'web/static/index.html'), 'web/static'),
        (str(ROOT / 'web/static/style.css'), 'web/static'),
        (str(ROOT / 'web/static/app.js'), 'web/static'),
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
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'apscheduler.triggers.interval',
        'apscheduler.triggers.cron',
        'cloudscraper',
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
    icon=str(ROOT / 'icon.png') if (ROOT / 'icon.png').exists() else None,
)
