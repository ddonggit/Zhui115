# Zhui115 — 自动追剧 + 115 离线下载

基于 RSS 订阅自动监控剧集更新，磁力链接自动离线到 115 网盘，带 Web 管理界面。

---

## 方式三：Windows 桌面版（带窗口界面）

### 1. 安装依赖

```bash
pip install -r requirements.txt
pip install PyQt6 PyQt6-WebEngine pyinstaller
```

### 2. 打包

```bash
pyinstaller Zhui115.spec
```

打包完成后，`dist/Zhui115.exe` 即为 Windows 桌面程序。

> 详细打包说明见 [BUILD_WINDOWS.md](BUILD_WINDOWS.md)

### 3. 运行

双击 `dist/Zhui115.exe`：

- **主窗口**：内嵌浏览器显示 Web 管理界面
- **系统托盘**：关闭窗口后最小化到托盘，后台继续运行
- **数据目录**：`dist/data/`（与 exe 同级的 data 文件夹）

---

## 环境要求

| 项目 | 最低要求 |
|------|---------|
| Python | **3.12+**（p115client 强制要求） |
| 操作系统 | Linux / macOS / **Windows（桌面版）** |
| 磁盘 | 至少 100MB（不含下载文件） |
| 磁盘 | 至少 100MB（不含下载文件） |
| 网络 | 能访问 115.com、RSS 源 |
| Docker | 可选（推荐） |

---

## 方式一：Docker 部署（推荐）

### 1. 安装 Docker

**Linux (Ubuntu/Debian)：**
```bash
sudo apt update
sudo apt install docker.io docker-compose-plugin -y
```

**macOS / Windows：**
下载安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)

### 2. 创建数据目录

```bash
mkdir -p /path/to/Zhui115/data
```

> 路径可按需修改，但需要同步修改 `docker-compose.yaml` 中的 volume 映射。

### 3. 启动容器

```bash
cd Zhui115
docker compose up -d
```

### 4. 查看启动日志

```bash
docker logs zhui115 -f --tail 50
```

看到以下输出说明启动成功：
```
🚀 Zhui115 启动 (Web端口 8300)
Cookie 已配置: ❌
```

### 5. 访问 Web 界面

浏览器打开：**http://你的服务器IP:8300**

---

## 方式二：直接运行（无 Docker）

### 1. 安装 Python 3.12+

**Ubuntu/Debian：**
```bash
sudo apt install python3.12 python3.12-venv -y
```

**macOS（Homebrew）：**
```bash
brew install python@3.12
```

**Windows：**
从 [python.org](https://www.python.org/downloads/) 下载 Python 3.12+ 安装包

### 2. 创建虚拟环境并安装依赖

```bash
cd Zhui115

# 创建虚拟环境
python3.12 -m venv .venv

# 激活虚拟环境
# Linux/macOS:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 启动

```bash
python3 main.py
```

### 4. 更详细的启动选项

```bash
# 调试模式（日志更详细）
python3 main.py --debug

# 仅启动 Web 界面（不启动定时调度）
python3 main.py --web-only

# 仅启动定时调度（无 Web 界面）
python3 main.py --scheduler-only

# 单次检查所有 RSS 源（不启动服务）
python3 main.py --check-now

# 指定端口
python3 main.py --port 8300

# 通过环境变量控制日志级别
ZHUI115_LOG_LEVEL=DEBUG python3 main.py
```

---

## 首次配置

### 1. 配置 115 Cookie

打开 Web 界面 → **设置** 页面

需要填入 115 网盘的登录 Cookie。格式如下：

```
UID=xxx; CID=xxx; SEID=xxx; KID=xxx
```

**如何获取 Cookie：**

1. 浏览器打开 [115.com](https://115.com) 并登录
2. 按 F12 打开开发者工具
3. 切换到 **网络(Network)** 标签
4. 刷新页面，点击任意请求
5. 在请求头中找到 `Cookie:` 字段，复制其值

或者直接在浏览器地址栏输入：
```
javascript:alert(document.cookie)
```
复制弹出框中的内容。

> **安全提示：** Cookie 等同你的账号密码，不要分享给他人。

### 2. 添加 RSS 源

打开 Web 界面 → **RSS 源** 页面 → 点击"添加源"

**推荐 RSS 源：**

| 名称 | 地址 |
|------|------|
| 动漫花园-动画 | `https://share.dmhy.org/topics/rss/sort_id/2/rss.xml` |
| 动漫花园-日剧 | `https://share.dmhy.org/topics/rss/sort_id/6/rss.xml` |
| 萌番组 | `https://bangumi.moe/rss/latest` |

### 3. 高级过滤设置

添加 RSS 源时可以配置以下过滤条件：

| 字段 | 说明 |
|------|------|
| 包含关键词 | 标题必须包含这些词（支持正则） |
| 排除关键词 | 标题不能包含这些词 |
| 正则过滤 | 开启后关键词按正则匹配 |
| 集数从/到 | 只下载指定范围的集数（如 150-160） |
| 季数 | 只下载指定季的内容 |
| 自动跟进 | 自动记住已下载的最新集数 |

> **集数范围示例：** 设置 集数从=150 集数到=160，则只下载第150~160集，
> 识别不出集数的条目（如剧场版、OVA）会被自动跳过。

---

## 数据目录

```
Zhui115/data/
├── global.json         # 全局配置（Cookie、端口等）
├── sources.json        # RSS 源列表
├── zhui115.db          # SQLite 数据库（去重、任务记录）
└── backups/            # Web 界面生成的备份文件
```

---

## Web 界面功能

| 页面 | 功能 |
|------|------|
| **总览** | 统计概览、通知开关状态、系统状态（调度器/115连接/配额） |
| **RSS 源** | 添加/编辑/删除 RSS 源，测试源解析，设置过滤规则 |
| **离线任务** | 查看 4 种状态：等待提交 / 已提交 / 失败 / 已完成 |
| **重试队列** | 重试提交失败的链接 |
| **操作日志** | 查看所有操作记录 |
| **设置** | 配置 Cookie、保存目录、检查间隔、**Telegram 通知**、**TMDB 封面** |

---

## Telegram 通知

支持离线成功/失败、RSS 源失效时自动推送到 Telegram。

### 配置步骤

1. 在 Telegram 中搜索 [@BotFather](https://t.me/botfather)，创建新 Bot，获取 Token
2. 向你的 Bot 发送一条消息，然后访问 `https://api.telegram.org/bot<你的Token>/getUpdates` 获取 Chat ID
3. 在 Web 界面 → **设置** → **通知设置** 中填入 Token 和 Chat ID

### 通知类型

| 通知 | 说明 |
|------|------|
| 离线成功 | 115 离线下载完成时通知（含封面图） |
| 离线失败 | 重试耗尽后通知 |
| RSS 源失效 | 连续触发 Cloudflare 或连续失败时通知 |

### 封面图

通知消息会自动尝试附加封面图片，优先级：
1. **RSS 源自带封面**（如蜜柑计划的 media:thumbnail）
2. **TMDB API 搜索**（需在设置页配置 TMDB API Key）
3. **无图时仅发文字**（干净的标题 + 集数 + 清晰度）

免费申请 TMDB API Key：https://www.themoviedb.org/settings/api

---

## 数据备份

Web 界面 → **设置** → **数据管理**

- **备份数据：** 一键下载当前数据库
- **恢复数据：** 上传备份文件恢复
- **清理数据：** 删除超过保留天数的历史记录

---

## 日志查看

```bash
# Docker 部署
docker logs zhui115 -f --tail 100

# 设置日志级别（环境变量）
docker run -e ZHUI115_LOG_LEVEL=DEBUG ... zhui115

# 或修改 docker-compose.yaml 添加：
#   environment:
#     - ZHUI115_LOG_LEVEL=DEBUG
```

日志级别从低到高：`DEBUG` → `INFO` → `WARNING` → `ERROR`

---

## 常见问题

### Cookie 无效？
- 重新从浏览器获取最新的 Cookie
- 115.com 的 Cookie 会定期过期，需要重新登录获取

### RSS 源无法抓取？
- 源站可能被 Cloudflare 阻挡，系统有自动重试机制
- 确认 RSS 地址可以正常访问
- 检查日志中是否有 Cloudflare 相关的错误

### 磁力链接提交失败（错误码 20004）？
- 表示该磁力已经在 115 离线任务中，系统会自动视为成功

### 状态一直显示"已提交"不变？
- `sync_offline_status` 每 2 分钟同步一次 115 任务状态
- 检查日志是否有 `获取115离线任务列表失败` 的提示

---

## 项目结构

```
Zhui115/
├── main.py                 # 入口：启动 Web + 调度
├── desktop.py              # Windows 桌面版入口（PyQt6 窗口）
├── Zhui115.spec            # PyInstaller 打包配置
├── BUILD_WINDOWS.md        # Windows 桌面版构建说明
├── icon.png                # 应用图标
├── requirements.txt        # Python 依赖
├── Dockerfile              # Docker 构建文件
├── docker-compose.yaml     # Docker 编排
├── README.md               # 本文件
│
├── app/
│   ├── config.py           # 配置管理（JSON 读写）
│   ├── db.py               # 数据库层（SQLite，5 张表）
│   ├── rss.py              # RSS 抓取与解析（cloudscraper + UA池）
│   ├── offline115.py       # 115 网盘离线下载封装
│   ├── scheduler.py        # 定时调度（APScheduler）
│   │
│   └── web/
│       ├── server.py       # HTTP 服务器
│       ├── api.py          # RESTful API（20+ 接口）
│       └── static/         # 前端 SPA
│           ├── index.html
│           ├── style.css
│           └── app.js
│
└── data/                   # 运行时数据（Docker volume 挂载点）
    ├── global.json
    ├── sources.json
    └── zhui115.db
```

---

## 技术栈

- **后端：** Python 3.12+, APScheduler, p115client
- **Web：** ThreadingHTTPServer（无框架）
- **前端：** 原生 HTML/CSS/JS SPA（深色主题）
- **数据库：** SQLite
- **RSS 解析：** feedparser + cloudscraper
- **部署：** Docker / 直接运行
