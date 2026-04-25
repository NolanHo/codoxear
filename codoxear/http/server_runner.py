from __future__ import annotations

import http.server
import os
import signal
import socket
import socketserver
import threading
import traceback
import urllib.parse
from pathlib import Path
from typing import Any


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class ThreadingHTTPServerV6(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        v6only = getattr(socket, "IPV6_V6ONLY", None)
        if v6only is not None:
            self.socket.setsockopt(socket.IPPROTO_IPV6, v6only, 0)
        super().server_bind()


def make_handler(runtime: Any):
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "codoxear/0.1"

        def _send_bytes(
            self,
            data: bytes,
            ctype: str,
            *,
            cache_control: str = "no-store",
        ) -> None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", cache_control)
            if cache_control == "no-store":
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(data)

        def _send_path(self, path: Path) -> None:
            data = runtime.api.read_static_bytes(path)
            self._send_bytes(
                data,
                runtime.api.content_type_for_path(path),
                cache_control=runtime.api.cache_control_for_path(path),
            )

        def _send_static(self, rel: str) -> None:
            path = (runtime.api.STATIC_DIR / rel.lstrip("/")).resolve()
            if not runtime.api.is_path_within(runtime.api.STATIC_DIR.resolve(), path):
                self.send_error(404)
                return
            if not path.exists() or not path.is_file():
                self.send_error(404)
                return
            self._send_path(path)

        def _unauthorized(self) -> None:
            runtime.api.json_response(self, 401, {"error": "unauthorized"})

        def do_GET(self) -> None:
            try:
                u = urllib.parse.urlparse(self.path)
                path = u.path
                if runtime.api.URL_PREFIX:
                    if path == runtime.api.URL_PREFIX:
                        loc = runtime.api.URL_PREFIX + "/"
                        if u.query:
                            loc = loc + "?" + u.query
                        self.send_response(308)
                        self.send_header("Location", loc)
                        self.end_headers()
                        return
                    stripped = runtime.api.strip_url_prefix(runtime.api.URL_PREFIX, path)
                    if stripped is None:
                        self.send_error(404)
                        return
                    path = stripped
                for route_module in runtime.get_route_modules:
                    if route_module.handle_get(runtime, self, path, u):
                        return
                self.send_error(404)
            except Exception as exc:
                traceback.print_exc()
                runtime.api.json_response(
                    self,
                    500,
                    {"error": str(exc), "trace": traceback.format_exc()},
                )

        def do_POST(self) -> None:
            try:
                u = urllib.parse.urlparse(self.path)
                path = u.path
                if runtime.api.URL_PREFIX:
                    if path == runtime.api.URL_PREFIX:
                        loc = runtime.api.URL_PREFIX + "/"
                        if u.query:
                            loc = loc + "?" + u.query
                        self.send_response(308)
                        self.send_header("Location", loc)
                        self.end_headers()
                        return
                    stripped = runtime.api.strip_url_prefix(runtime.api.URL_PREFIX, path)
                    if stripped is None:
                        self.send_error(404)
                        return
                    path = stripped
                for route_module in runtime.post_route_modules:
                    if route_module.handle_post(runtime, self, path, u):
                        return
                self.send_error(404)
            except KeyError:
                runtime.api.json_response(self, 404, {"error": "unknown session"})
            except Exception as exc:
                traceback.print_exc()
                runtime.api.json_response(
                    self,
                    500,
                    {"error": str(exc), "trace": traceback.format_exc()},
                )

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return Handler


def main(runtime: Any, handler_cls: type[http.server.BaseHTTPRequestHandler]) -> None:
    os.makedirs(runtime.api.APP_DIR, exist_ok=True)
    os.makedirs(runtime.api.UPLOAD_DIR, exist_ok=True)
    try:
        runtime.api.require_password()
    except Exception as exc:
        runtime.api.sys.stderr.write(f"error: {exc}\n")
        raise SystemExit(2)

    host = runtime.api.DEFAULT_HOST
    server: ThreadingHTTPServer
    if ":" in host:
        server = ThreadingHTTPServerV6((host, runtime.api.DEFAULT_PORT), handler_cls)
    else:
        server = ThreadingHTTPServer((host, runtime.api.DEFAULT_PORT), handler_cls)

    def _sigterm(_signo: int, _frame: Any) -> None:
        runtime.manager.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)

    server.serve_forever()
