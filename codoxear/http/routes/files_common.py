from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any

from ...runtime import ServerRuntime


def send_inline_blob(runtime: ServerRuntime, handler: Any, path_obj: Path) -> None:
    raw = path_obj.read_bytes()
    kind, ctype = runtime._file_kind(path_obj, raw)
    if kind not in {"image", "pdf"} or ctype is None:
        runtime._json_response(handler, 400, {"error": "file is not previewable inline"})
        return
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header(
        "Content-Disposition",
        f"inline; filename*=UTF-8''{urllib.parse.quote(path_obj.name, safe='')}",
    )
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Expires", "0")
    handler.end_headers()
    handler.wfile.write(raw)


def read_json_object(
    runtime: ServerRuntime,
    handler: Any,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    body = runtime._read_body(handler, limit=limit or 2 * 1024 * 1024)
    body_text = body.decode("utf-8")
    if not body_text.strip():
        raise ValueError("empty request body")
    obj = json.loads(body_text)
    if not isinstance(obj, dict):
        raise ValueError("invalid json body (expected object)")
    return obj


def session_id_from_path(path: str) -> str:
    parts = path.split("/")
    return parts[3] if len(parts) >= 4 else ""


def require_query_value(
    runtime: ServerRuntime,
    handler: Any,
    query: dict[str, list[str]],
    key: str,
) -> str | None:
    values = query.get(key)
    if not values or not values[0]:
        runtime._json_response(handler, 400, {"error": f"{key} required"})
        return None
    return values[0]
