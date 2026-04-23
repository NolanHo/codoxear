from __future__ import annotations

import json
from typing import Any

from ...runtime import ServerRuntime


def read_json_object(runtime: ServerRuntime, handler: Any) -> dict[str, Any]:
    body = runtime._read_body(handler)
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
