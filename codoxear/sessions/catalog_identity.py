from __future__ import annotations

from typing import Any

from ..agent_backend import normalize_agent_backend
from ..page_state_sqlite import PageStateDB, SessionRef


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip()
    return out or None


def _parse_historical_session_id(session_id: str) -> tuple[str, str] | None:
    raw = str(session_id or "").strip()
    if not raw.startswith("history:"):
        return None
    _prefix, backend, resume_session_id = (
        raw.split(":", 2) if raw.count(":") >= 2 else ("", "", "")
    )
    backend_clean = normalize_agent_backend(backend, default="codex")
    resume_clean = _clean_optional_text(resume_session_id)
    if not resume_clean:
        return None
    return backend_clean, resume_clean


def runtime_session_id_for_identifier(manager: Any, session_id: str) -> str | None:
    target = _clean_optional_text(session_id)
    if target is None:
        return None
    with manager._lock:
        if target in manager._sessions:
            return target
        matches: list[tuple[float, str]] = []
        for runtime_id, session in manager._sessions.items():
            ref = manager._page_state_ref_for_session(session)
            if ref is not None and ref[1] == target:
                matches.append((float(session.start_ts or 0.0), runtime_id))
                continue
            thread_id = _clean_optional_text(session.thread_id)
            if thread_id == target:
                matches.append((float(session.start_ts or 0.0), runtime_id))
        if not matches:
            return None
        matches.sort(key=lambda item: (-item[0], item[1]))
        return matches[0][1]


def durable_session_id_for_identifier(manager: Any, session_id: str) -> str | None:
    runtime_id = runtime_session_id_for_identifier(manager, session_id)
    if runtime_id is not None:
        with manager._lock:
            session = manager._sessions.get(runtime_id)
        if session is not None:
            return manager._durable_session_id_for_session(session)
    target = _clean_optional_text(session_id)
    return target if target is not None else None


def page_state_ref_for_session_id(manager: Any, session_id: str) -> SessionRef | None:
    runtime_id = runtime_session_id_for_identifier(manager, session_id)
    if runtime_id is not None:
        with manager._lock:
            session = manager._sessions.get(runtime_id)
        if session is not None:
            return manager._page_state_ref_for_session(session)
    parsed = _parse_historical_session_id(session_id)
    if parsed is not None:
        return parsed
    target = _clean_optional_text(session_id)
    db = getattr(manager, "_page_state_db", None)
    if target is not None and isinstance(db, PageStateDB):
        matches = [ref for ref in db.known_session_refs() if ref[1] == target]
        if len(matches) == 1:
            return matches[0]
    return None


def get_session(manager: Any, session_id: str) -> Any | None:
    runtime_id = runtime_session_id_for_identifier(manager, session_id)
    if runtime_id is None:
        return None
    with manager._lock:
        return manager._sessions.get(runtime_id)


def listed_session_row(manager: Any, session_id: str) -> dict[str, Any] | None:
    for row in manager.list_sessions():
        if str(row.get("session_id") or "") == session_id:
            return dict(row)
    return None
