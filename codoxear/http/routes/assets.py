from __future__ import annotations

from typing import Any

from ...runtime import ServerRuntime
from ...runtime_facade import build_runtime_facade


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    facade = build_runtime_facade(runtime)
    if path == "/favicon.ico":
        resolved = facade.resolve_public_web_asset("favicon.ico")
        if resolved is not None:
            handler._send_path(resolved)
            return True
        handler._send_static("favicon.png")
        return True
    if path == "/manifest.webmanifest":
        resolved = facade.resolve_public_web_asset("manifest.webmanifest")
        if resolved is None:
            handler.send_error(404)
            return True
        handler._send_path(resolved)
        return True
    if path == "/service-worker.js":
        resolved = facade.resolve_public_web_asset("service-worker.js")
        if resolved is None:
            handler.send_error(404)
            return True
        handler._send_path(resolved)
        return True
    if path == "/app.js":
        handler._send_static("app.js")
        return True
    if path == "/app.css":
        handler._send_static("app.css")
        return True
    if path == "/favicon.png":
        resolved = facade.resolve_public_web_asset("favicon.png")
        if resolved is not None:
            handler._send_path(resolved)
            return True
        handler._send_static("favicon.png")
        return True
    if path == "/":
        body, ctype = facade.read_web_index()
        handler._send_bytes(body.encode("utf-8"), ctype)
        return True
    if path.startswith("/assets/") and not facade.use_legacy_web():
        served_dist_dir = facade.served_web_dist_dir()
        if served_dist_dir is not None:
            candidate = (served_dist_dir / path.lstrip("/")).resolve()
            if facade.is_path_within(served_dist_dir.resolve(), candidate) and candidate.is_file():
                handler._send_path(candidate)
                return True
        handler.send_error(404)
        return True
    if (
        not facade.use_legacy_web()
        and path.startswith("/")
        and "/" not in path[1:]
        and not path.startswith("/api/")
    ):
        resolved = facade.resolve_public_web_asset(path)
        if resolved is not None:
            handler._send_path(resolved)
            return True
    if path.startswith("/static/"):
        handler._send_static(path[len("/static/") :])
        return True
    return False
