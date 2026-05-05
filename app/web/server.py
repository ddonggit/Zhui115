"""Zhui115 Web 服务器

基于 ThreadingHTTPServer，前后端分离。
"""

import json
import logging
import mimetypes
import os
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

from .api import route

logger = logging.getLogger("zhui115.web")

STATIC_DIR = Path(__file__).parent.parent / "static"


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器"""
    allow_reuse_address = True
    daemon_threads = True


class Zhui115Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)

    def _send_static(self, path: str):
        """提供静态文件服务（带路径穿越防护）"""
        # 路径穿越防护
        try:
            resolved = (STATIC_DIR / path.lstrip("/")).resolve()
            resolved.relative_to(STATIC_DIR.resolve())
        except (ValueError, RuntimeError):
            self._send_error(403, "Forbidden")
            return

        if not resolved.exists() or not resolved.is_file():
            self._send_error(404, "Not Found")
            return

        content_type, _ = mimetypes.guess_type(str(resolved))
        if content_type is None:
            content_type = "application/octet-stream"

        try:
            data = resolved.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            self._send_error(500, "IO Error")

    def _send_api(self, status_code, data, content_type, extra_headers=None):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, code, msg):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(msg.encode("utf-8"))

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            return self.rfile.read(length)
        return b""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}

        # API 路由
        if path.startswith("/api/"):
            try:
                status, data, ctype, headers = self._route_result("GET", path, query=query)
                self._send_api(status, data, ctype, headers)
            except Exception as e:
                logger.exception("API 错误")
                self._send_error(500, str(e))
            return

        # 静态文件
        if path == "/" or path == "":
            path = "/index.html"
        self._send_static(path)

    def _route_result(self, method, path, body=b"", query=None):
        """调用 route，兼容 3 元组或 4 元组返回值"""
        result = route(method, path, body, query or {})
        if len(result) == 4:
            return result
        return (*result, {})

    def do_POST(self):
        body = self._read_body()
        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}

        if path.startswith("/api/"):
            try:
                status, data, ctype, headers = self._route_result("POST", path, body, query)
                self._send_api(status, data, ctype, headers)
            except Exception as e:
                logger.exception("API 错误")
                self._send_error(500, str(e))
            return

        self._send_error(404, "Not Found")

    def do_PUT(self):
        body = self._read_body()
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            try:
                status, data, ctype, headers = self._route_result("PUT", path, body)
                self._send_api(status, data, ctype, headers)
            except Exception as e:
                logger.exception("API 错误")
                self._send_error(500, str(e))
            return

        self._send_error(404, "Not Found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            try:
                status, data, ctype, headers = self._route_result("DELETE", path)
                self._send_api(status, data, ctype, headers)
            except Exception as e:
                logger.exception("API 错误")
                self._send_error(500, str(e))
            return

        self._send_error(404, "Not Found")

    def do_OPTIONS(self):
        """CORS preflight"""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def run(host: str = "0.0.0.0", port: int = 8300):
    """启动 Web 服务器"""
    server = ThreadingHTTPServer((host, port), Zhui115Handler)
    logger.info("Web 服务器启动: http://%s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
