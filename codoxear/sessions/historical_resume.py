from __future__ import annotations

from typing import Any

from ..agent_backend import normalize_agent_backend


def clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip()
    return out or None


def parse_historical_session_id(session_id: str) -> tuple[str, str] | None:
    raw = str(session_id or "").strip()
    if not raw.startswith("history:"):
        return None
    _prefix, backend, resume_session_id = (
        raw.split(":", 2) if raw.count(":") >= 2 else ("", "", "")
    )
    backend_clean = normalize_agent_backend(backend, default="codex")
    resume_clean = clean_optional_text(resume_session_id)
    if not resume_clean:
        return None
    return backend_clean, resume_clean


def historical_session_row(manager: Any, session_id: str) -> dict[str, Any] | None:
    parsed = parse_historical_session_id(session_id)
    if parsed is None:
        return None
    backend, resume_session_id = parsed
    for row in manager.list_sessions():
        if normalize_agent_backend(row.get("agent_backend", row.get("backend")), default="codex") != backend:
            continue
        if clean_optional_text(row.get("resume_session_id")) != resume_session_id:
            continue
        out = dict(row)
        out["session_id"] = session_id
        out["resume_session_id"] = resume_session_id
        out["historical"] = True
        return out
    return None


def listed_session_row(manager: Any, session_id: str) -> dict[str, Any] | None:
    for row in manager.list_sessions():
        if str(row.get("session_id") or "") == session_id:
            return dict(row)
    return None


def resume_historical_pi_session(manager: Any, session_id: str) -> dict[str, Any] | None:
    historical_row = historical_session_row(manager, session_id)
    if historical_row is None and manager.runtime_session_id_for_identifier(session_id) is None:
        listed_row = listed_session_row(manager, session_id)
        if isinstance(listed_row, dict) and listed_row.get("historical"):
            historical_row = listed_row
    if historical_row is None:
        return None

    backend = normalize_agent_backend(
        historical_row.get("agent_backend", historical_row.get("backend")),
        default="codex",
    )
    if backend != "pi":
        raise KeyError("unknown session")
    cwd = clean_optional_text(historical_row.get("cwd"))
    resume_session_id = clean_optional_text(historical_row.get("resume_session_id"))
    if cwd is None or resume_session_id is None:
        raise ValueError("historical session is missing resume metadata")
    spawn_res = manager.spawn_web_session(
        cwd=cwd,
        backend="pi",
        resume_session_id=resume_session_id,
    )
    manager.discover_existing(force=True, skip_invalid_sidecars=True)
    live_runtime_id = clean_optional_text(spawn_res.get("runtime_id"))
    live_session_id = clean_optional_text(spawn_res.get("session_id"))
    if live_runtime_id is None or live_session_id is None:
        raise RuntimeError("spawned session did not return session identities")
    if manager.runtime_session_id_for_identifier(live_runtime_id) is None:
        raise RuntimeError("spawned session is not yet discoverable")
    return {
        "runtime_id": live_runtime_id,
        "session_id": live_session_id,
        "backend": "pi",
    }
