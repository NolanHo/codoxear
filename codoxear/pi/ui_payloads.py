from __future__ import annotations

from typing import Any


_PI_DIALOG_UI_METHODS = {"select", "confirm", "input", "editor"}

_PI_BUILTIN_COMMANDS = [
    {"name": "login", "description": "OAuth authentication", "source": "builtin"},
    {"name": "logout", "description": "OAuth authentication", "source": "builtin"},
    {"name": "model", "description": "Switch models", "source": "builtin"},
    {
        "name": "scoped-models",
        "description": "Enable or disable models for Ctrl+P cycling",
        "source": "builtin",
    },
    {
        "name": "settings",
        "description": "Thinking level, theme, message delivery, transport",
        "source": "builtin",
    },
    {"name": "resume", "description": "Pick from previous sessions", "source": "builtin"},
    {"name": "new", "description": "Start a new session", "source": "builtin"},
    {"name": "name", "description": "Set session display name", "source": "builtin"},
    {"name": "session", "description": "Show session info", "source": "builtin"},
    {
        "name": "tree",
        "description": "Jump to any point in the session and continue from there",
        "source": "builtin",
    },
    {"name": "fork", "description": "Create a new session from the current branch", "source": "builtin"},
    {"name": "compact", "description": "Manually compact context", "source": "builtin"},
    {"name": "copy", "description": "Copy last assistant message to clipboard", "source": "builtin"},
    {"name": "export", "description": "Export session to HTML", "source": "builtin"},
    {
        "name": "share",
        "description": "Upload as a private GitHub gist with shareable HTML link",
        "source": "builtin",
    },
    {"name": "reload", "description": "Reload keybindings, extensions, skills, prompts, and context files", "source": "builtin"},
    {"name": "hotkeys", "description": "Show all keyboard shortcuts", "source": "builtin"},
    {"name": "changelog", "description": "Display version history", "source": "builtin"},
    {"name": "quit", "description": "Quit pi", "source": "builtin"},
    {"name": "exit", "description": "Quit pi", "source": "builtin"},
]


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
    filtered: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(commands, list):
        for item in commands:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str):
                continue
            clean_name = name.strip()
            if not clean_name or clean_name in seen:
                continue
            clean_item: dict[str, Any] = {"name": clean_name}
            description = item.get("description")
            if isinstance(description, str) and description.strip():
                clean_item["description"] = description.strip()
            source = item.get("source")
            if isinstance(source, str) and source.strip():
                clean_item["source"] = source.strip()
            filtered.append(clean_item)
            seen.add(clean_name)
    for item in _PI_BUILTIN_COMMANDS:
        name = item["name"]
        if name in seen:
            continue
        filtered.append(dict(item))
        seen.add(name)
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
