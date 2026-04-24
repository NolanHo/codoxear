from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any

from ...runtime_facade import RuntimeFacade


def send_inline_blob(facade: RuntimeFacade, handler: Any, path_obj: Path) -> None:
    raw = path_obj.read_bytes()
    kind, ctype = facade.file_kind(path_obj, raw)
    if kind not in {"image", "pdf"} or ctype is None:
        facade.json_response(handler, 400, {"error": "file is not previewable inline"})
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
    facade: RuntimeFacade,
    handler: Any,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    body = facade.read_body(handler, limit=limit or 2 * 1024 * 1024)
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
    facade: RuntimeFacade,
    handler: Any,
    query: dict[str, list[str]],
    key: str,
) -> str | None:
    values = query.get(key)
    if not values or not values[0]:
        facade.json_response(handler, 400, {"error": f"{key} required"})
        return None
    return values[0]
