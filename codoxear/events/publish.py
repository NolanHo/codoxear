from __future__ import annotations

from typing import Any


def publish_invalidate_event(
    event_hub: Any,
    clean_optional_text: Any,
    event_type: str,
    *,
    session_id: str | None = None,
    runtime_id: str | None = None,
    reason: str,
    hints: dict[str, Any] | None = None,
    coalesce_ms: int = 300,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "type": event_type,
        "reason": str(reason).strip() or "update",
        "_coalesce_ms": int(coalesce_ms),
        "_coalesce_key": (str(event_type), str(session_id or "")),
    }
    clean_session_id = clean_optional_text(session_id)
    clean_runtime_id = clean_optional_text(runtime_id)
    if clean_session_id is not None:
        payload["session_id"] = clean_session_id
    if clean_runtime_id is not None:
        payload["runtime_id"] = clean_runtime_id
    if isinstance(hints, dict) and hints:
        payload["hints"] = dict(hints)
    return event_hub.publish(payload)


def publish_sessions_invalidate(
    event_hub: Any,
    clean_optional_text: Any,
    *,
    reason: str,
    coalesce_ms: int = 500,
) -> dict[str, Any] | None:
    return publish_invalidate_event(
        event_hub,
        clean_optional_text,
        "sessions.invalidate",
        reason=reason,
        coalesce_ms=coalesce_ms,
    )


def publish_session_live_invalidate(
    event_hub: Any,
    clean_optional_text: Any,
    session_id: str,
    *,
    runtime_id: str | None = None,
    reason: str,
    hints: dict[str, Any] | None = None,
    coalesce_ms: int = 300,
) -> dict[str, Any] | None:
    return publish_invalidate_event(
        event_hub,
        clean_optional_text,
        "session.live.invalidate",
        session_id=session_id,
        runtime_id=runtime_id,
        reason=reason,
        hints=hints,
        coalesce_ms=coalesce_ms,
    )


def publish_session_workspace_invalidate(
    event_hub: Any,
    clean_optional_text: Any,
    session_id: str,
    *,
    runtime_id: str | None = None,
    reason: str,
    coalesce_ms: int = 300,
) -> dict[str, Any] | None:
    return publish_invalidate_event(
        event_hub,
        clean_optional_text,
        "session.workspace.invalidate",
        session_id=session_id,
        runtime_id=runtime_id,
        reason=reason,
        coalesce_ms=coalesce_ms,
    )


def publish_session_transport_invalidate(
    event_hub: Any,
    clean_optional_text: Any,
    session_id: str,
    *,
    runtime_id: str | None = None,
    reason: str,
    coalesce_ms: int = 300,
) -> dict[str, Any] | None:
    return publish_invalidate_event(
        event_hub,
        clean_optional_text,
        "session.transport.invalidate",
        session_id=session_id,
        runtime_id=runtime_id,
        reason=reason,
        coalesce_ms=coalesce_ms,
    )
