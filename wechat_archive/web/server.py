import json
import sqlite3
import webbrowser
from dataclasses import asdict, is_dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlsplit

from .. import __version__
from ..database.db import default_data_dir
from ..demo import seed_demo
from ..errors import ConflictError, NotFoundError, ValidationError
from ..services import ChatService
from ..services.browse_service import BrowseService

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    raise TypeError(type(value).__name__)


class ArchiveHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, service, port, demo):
        self.service = service
        self.reader = BrowseService(service)
        self.demo = demo
        super().__init__(("127.0.0.1", port), ArchiveHandler)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}/"


class ArchiveHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        # 请求可能包含私人搜索词，不把路径和参数写入终端日志。
        pass

    def _respond(self, status, data, content_type="application/json; charset=utf-8"):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status, kind, message):
        self._respond(status, {"error": {"type": kind, "message": message}})

    def _local_request(self):
        hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host", "").lower() not in hosts:
            self._error(403, "Forbidden", "此页面只允许从本机地址访问")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{host}" for host in hosts}:
            self._error(403, "Forbidden", "不允许其他网页读取聊天数据")
            return False
        return True

    @staticmethod
    def _parameters(query, allowed, required=()):
        raw = parse_qs(query, keep_blank_values=True, max_num_fields=20)
        if any(key not in allowed for key in raw) or any(len(values) != 1 for values in raw.values()):
            raise ValidationError("查询参数包含未知字段或重复字段")
        result = {}
        numbers = {"user_id", "peer_id", "limit", "offset"}
        mapping = {"q": "keyword", "start": "start_time", "end": "end_time"}
        for key, values in raw.items():
            value = values[0]
            if key in numbers:
                try:
                    result[key] = int(value)
                except ValueError as exc:
                    raise ValidationError(f"{key} 必须是整数") from exc
            elif value:
                result[mapping.get(key, key)] = value
        if any(key not in result for key in required):
            raise ValidationError("请指定查看身份 user_id")
        return result

    def do_GET(self):
        if not self._local_request():
            return
        try:
            if len(self.path) > 8192:
                raise ValidationError("查询内容过长")
            parsed = urlsplit(self.path)
            if parsed.path in ASSETS:
                name, mime = ASSETS[parsed.path]
                self._respond(200, files("wechat_archive.web").joinpath("static", name).read_bytes(), mime)
            elif parsed.path == "/api/status":
                self._parameters(parsed.query, set())
                self._respond(200, {"version": __version__, "mode": "demo" if self.server.demo else "archive", "database": self.server.service.database.path.name, **self.server.service.stats()})
            elif parsed.path == "/api/users":
                args = self._parameters(parsed.query, {"limit", "offset"})
                self._respond(200, self.server.reader.users(**args))
            elif parsed.path == "/api/contacts":
                args = self._parameters(parsed.query, {"user_id", "q", "limit", "offset"}, ("user_id",))
                self._respond(200, self.server.reader.contacts(**args))
            elif parsed.path == "/api/messages":
                args = self._parameters(parsed.query, {"user_id", "peer_id", "q", "start", "end", "limit", "offset"}, ("user_id",))
                self._respond(200, self.server.reader.messages(**args))
            else:
                self._error(404, "NotFound", "页面或接口不存在")
        except (ValidationError, ValueError) as exc:
            self._error(400, "ValidationError", str(exc))
        except NotFoundError as exc:
            self._error(404, "NotFoundError", str(exc))
        except ConflictError as exc:
            self._error(409, "ConflictError", str(exc))
        except (OSError, sqlite3.Error):
            self._error(500, "StorageError", "无法读取本地数据，请检查数据库和启动窗口")

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if self._local_request():
            self._error(405, "MethodNotAllowed", "聊天浏览页面只提供读取接口")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST


def make_server(path=None, *, port=0, demo=False):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValidationError("端口必须是 0 到 65535 的整数；0 表示自动选择可用端口")
    if demo and path is None:
        path = default_data_dir() / "demo.db"
    service = ChatService(path)
    if demo:
        seed_demo(service)
    return ArchiveHTTPServer(service, port, demo)


def run_server(path=None, *, port=8765, demo=False, open_browser=False):
    server = make_server(path, port=port, demo=demo)
    print(f"聊天浏览器已启动：{server.url}", flush=True)
    print(f"正在查看：{'虚构演示数据' if demo else '本地归档数据'}（{server.service.database.path.name}）", flush=True)
    print("请保留此窗口；按 Ctrl+C 关闭服务。", flush=True)
    try:
        if open_browser:
            webbrowser.open(server.url)
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\n聊天浏览器已关闭。", flush=True)
    finally:
        server.server_close()
