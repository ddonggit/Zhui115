# Zhui115 Docker 部署指南

## 快速开始

### 1. 构建镜像

```bash
cd Zhui115
docker compose build
```

### 2. 启动

```bash
docker compose up -d
```

### 3. 访问

浏览器打开 `http://你的IP:8300`

### 4. 配置

首次使用需要配置 **115 Cookie**：
1. 打开设置页面
2. 粘贴你的 115 Cookie（格式: `UID=...; CID=...; SEID=...; KID=...`）
3. 点击保存

> 如何获取 115 Cookie？登录 115.com 后，在浏览器开发者工具中复制 Cookie 即可。

### 5. 添加 RSS 源

转到"RSS 源"页面，点击"添加源"。

推荐源：
- **动漫花园 动画**: `https://share.dmhy.org/topics/rss/sort_id/2/rss.xml`
- **动漫花园 日剧**: `https://share.dmhy.org/topics/rss/sort_id/6/rss.xml`
- **萌番组**: `https://bangumi.moe/rss/latest`
- **bt4gprx 搜索**: `https://bt4gprx.com/search?q=关键词&page=rss`

---

## 目录结构

```
Zhui115/
├── main.py              # 入口
├── app/
│   ├── config.py        # 配置管理
│   ├── db.py            # 数据库
│   ├── rss.py           # RSS 解析
│   ├── offline115.py    # 115 离线下载
│   ├── scheduler.py     # 定时调度
│   └── web/
│       ├── api.py       # RESTful API
│       └── server.py    # HTTP 服务器
├── static/
│   ├── index.html       # Web 前端
│   ├── style.css        # 样式
│   └── app.js           # 前端逻辑
├── data/                # 持久化数据（Docker volume）
│   ├── global.json      # 全局配置
│   ├── sources.json     # RSS 源配置
│   ├── zhui115.db       # 数据库
│   └── backups/         # 备份文件
├── Dockerfile
├── docker-compose.yaml
└── requirements.txt
```

---

## 数据备份

通过 Web 界面（设置 → 数据管理 → 备份数据）可以一键备份。

备份文件保存在 `data/backups/` 目录。

## 端口

默认 8300，可通过 `docker-compose.yaml` 修改映射。
