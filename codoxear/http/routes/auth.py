from __future__ import annotations

import json
from typing import Any
from ...runtime import ServerRuntime

def handle_get(runtime: ServerRuntime, handler: Any, path: str, _u: Any) -> bool:
    sv = runtime
    if path != "/api/me":
        return False
    if not sv.api.require_auth(handler):
        handler._unauthorized()
        return True
    sv.api.json_response(handler, 200, {"ok": True})
    return True



def handle_post(runtime: ServerRuntime, handler: Any, path: str, _u: Any) -> bool:
    sv = runtime
    if path == "/api/login":
        body = sv.api.read_body(handler)
        body_text = body.decode("utf-8")
        if not body_text.strip():
            raise ValueError("empty request body")
        obj = json.loads(body_text)
        if not isinstance(obj, dict):
            raise ValueError("invalid json body (expected object)")
        pw = obj.get("password")
        if not isinstance(pw, str) or not sv.api.is_same_password(pw):
            sv.api.json_response(handler, 403, {"error": "bad password"})
            return True
        handler.send_response(200)
        sv.api.set_auth_cookie(handler)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.end_headers()
        handler.wfile.write(b'{"ok":true}')
        return True
    if path == "/api/logout":
        if not sv.api.require_auth(handler):
            handler._unauthorized()
            return True
        handler.send_response(200)
        handler.send_header(
            "Set-Cookie",
            f"{sv.api.COOKIE_NAME}=deleted; Path={sv.api.COOKIE_PATH}; Max-Age=0; HttpOnly; SameSite=Strict",
        )
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.end_headers()
        handler.wfile.write(b'{"ok":true}')
        return True
    return False
