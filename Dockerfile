# Zhui115 Dockerfile
# 基于 p115client 的自动追剧离线下载工具

FROM python:3.12-slim

LABEL maintainer="Zhui115" \
      description="自动追剧 RSS 监控 + 115 离线下载"

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 数据目录
VOLUME /app/data

# 暴露 Web 端口
EXPOSE 8300

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8300/api/global')" || exit 1

# 启动
CMD ["python3", "main.py"]
