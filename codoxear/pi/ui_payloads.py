from __future__ import annotations

from typing import Any


_PI_DIALOG_UI_METHODS = {"select", "confirm", "input", "editor"}


def sanitize_pi_ui_state_payload(payload: dict[str, Any]) -> dict[str, Any]:
    requests = payload.get("requests")
    if not isinstance(requests, list):
        return {"requests": []}
    filtered = []
    for item in requests:
        if not isinstance(item, dict):
            continue
        method = item.get("method")
        if not isinstance(method, str) or method not in _PI_DIALOG_UI_METHODS:
            continue
        filtered.append(item)
    return {"requests": filtered}


def todo_snapshot_payload_for_session(runtime: Any, session: Any) -> dict[str, Any]:
    empty = {"available": False, "error": False, "items": []}
    read_error = {"available": False, "error": True, "items": []}
    if session.backend != "pi" or session.session_path is None:
        return empty
    try:
        snapshot = runtime.api.pi_messages.read_latest_pi_todo_snapshot(session.session_path)
    except FileNotFoundError:
        return empty
    except OSError as exc:
        if exc.errno == runtime.api.errno.ENOENT:
            return empty
        return read_error
    if snapshot is None:
        return empty
    return {
        "available": True,
        "error": False,
        "items": snapshot.get("items", []),
        "counts": snapshot.get("counts", {}),
        "progress_text": snapshot.get("progress_text", ""),
    }


def sanitize_pi_commands_payload(payload: dict[str, Any]) -> dict[str, Any]:
    commands = payload.get("commands")
    if not isinstance(commands, list):
        return {"commands": []}
    filtered: list[dict[str, Any]] = []
    for item in commands:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        clean_name = name.strip()
        if not clean_name:
            continue
        clean_item: dict[str, Any] = {"name": clean_name}
        description = item.get("description")
        if isinstance(description, str) and description.strip():
            clean_item["description"] = description.strip()
        source = item.get("source")
        if isinstance(source, str) and source.strip():
            clean_item["source"] = source.strip()
        filtered.append(clean_item)
    return {"commands": filtered}


def legacy_pi_ui_response_text(payload: dict[str, Any]) -> str | None:
    if payload.get("cancelled") is True:
        return None
    confirmed = payload.get("confirmed")
    if isinstance(confirmed, bool):
        return "yes" if confirmed else "no"
    value = payload.get("value")
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        parts = []
        for item in value:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if not text:
                continue
            parts.append(text)
        if parts:
            return ", ".join(parts)
    return None
