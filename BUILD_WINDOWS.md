# Zhui115 Windows 桌面版 — 构建说明

## 前置依赖

```bash
# 1. 安装 Python 3.12+
#    下载: https://www.python.org/downloads/

# 2. 安装项目依赖
pip install -r requirements.txt

# 3. 安装桌面版额外依赖
pip install PyQt6 PyQt6-WebEngine pyinstaller
```

## 应用图标（可选）

准备一个 256x256 的 PNG 图标，命名为 `icon.png` 放在项目根目录。
如果没有，可以使用在线工具生成一个，或者跳过（使用默认图标）。

## 打包

```bash
# 方式一：使用 spec 文件（推荐）
pyinstaller Zhui115.spec

# 方式二：直接命令行打包
pyinstaller --onefile --windowed --name Zhui115 ^
  --add-data "web/static;web/static" ^
  --hidden-import PyQt6.QtWebEngineWidgets ^
  --hidden-import apscheduler.triggers.interval ^
  --hidden-import apscheduler.triggers.cron ^
  desktop.py
```

打包完成后，在 `dist/Zhui115.exe` 找到生成的文件。

## 运行

双击 `dist/Zhui115.exe` 即可启动。

- 主窗口打开后自动加载 Web 界面
- 关闭窗口 → 最小化到系统托盘
- 双击托盘图标 → 恢复窗口
- 托盘右键 → 退出

## 数据目录

数据保存在 `dist/data/` 目录（与 exe 同级的 data 文件夹）。

```
Zhui115/
├── Zhui115.exe          # 主程序
└── data/
    ├── global.json      # 配置（Cookie、端口等）
    ├── sources.json     # RSS 源列表
    ├── zhui115.db       # 数据库
    └── zhui115.log      # 日志
```

## 常见问题

**Q: 启动后弹"Web 服务启动失败"？**
A: 端口 8300 被占用，关闭其他占用该端口的程序再试。
   或者修改 `data/config.json` 中的 `web_port` 为其他值。

**Q: 双击没反应？**
A: 查看 `data/zhui115.log` 中的错误日志。

**Q: 打包后 exe 太大（~200MB）？**
A: PyQt6 + Chromium 引擎确实比较大。可以尝试去掉 QWebEngineView，
   改为启动后自动打开系统默认浏览器（但就不是"带窗口"了）。
