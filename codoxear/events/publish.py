from __future__ import annotations

from dataclasses import dataclass
from types import FunctionType
from typing import Any

from ..runtime import ServerRuntime


def _runtime_wrapper(runtime: ServerRuntime, name: str) -> Any | None:
    module = getattr(runtime, "module", None)
    if module is None:
        return None
    wrapper = getattr(module, name, None)
    if not callable(wrapper):
        return None
    if (
        isinstance(wrapper, FunctionType)
        and getattr(wrapper, "__module__", None) == getattr(module, "__name__", None)
        and getattr(wrapper, "__name__", None) == name
    ):
        return None
    return wrapper


@dataclass(slots=True)
class EventPublishService:
    runtime: ServerRuntime

    def publish_sessions_invalidate(
        self,
        *,
        reason: str,
        coalesce_ms: int = 500,
    ) -> dict[str, Any] | None:
        wrapper = _runtime_wrapper(self.runtime, "_publish_sessions_invalidate")
        if wrapper is not None:
            return wrapper(reason=reason, coalesce_ms=coalesce_ms)
        return publish_sessions_invalidate(
            self.runtime.event_hub,
            self.runtime.api.clean_optional_text,
            reason=reason,
            coalesce_ms=coalesce_ms,
        )

    def publish_session_live_invalidate(
        self,
        session_id: str,
        *,
        runtime_id: str | None = None,
        reason: str,
        hints: dict[str, Any] | None = None,
        coalesce_ms: int = 300,
    ) -> dict[str, Any] | None:
        wrapper = _runtime_wrapper(self.runtime, "_publish_session_live_invalidate")
        if wrapper is not None:
            return wrapper(
                session_id,
                runtime_id=runtime_id,
                reason=reason,
                hints=hints,
                coalesce_ms=coalesce_ms,
            )
        return publish_session_live_invalidate(
            self.runtime.event_hub,
            self.runtime.api.clean_optional_text,
            session_id,
            runtime_id=runtime_id,
            reason=reason,
            hints=hints,
            coalesce_ms=coalesce_ms,
        )

    def publish_session_workspace_invalidate(
        self,
        session_id: str,
        *,
        runtime_id: str | None = None,
        reason: str,
        coalesce_ms: int = 300,
    ) -> dict[str, Any] | None:
        wrapper = _runtime_wrapper(self.runtime, "_publish_session_workspace_invalidate")
        if wrapper is not None:
            return wrapper(
                session_id,
                runtime_id=runtime_id,
                reason=reason,
                coalesce_ms=coalesce_ms,
            )
        return publish_session_workspace_invalidate(
            self.runtime.event_hub,
            self.runtime.api.clean_optional_text,
            session_id,
            runtime_id=runtime_id,
            reason=reason,
            coalesce_ms=coalesce_ms,
        )

    def publish_session_transport_invalidate(
        self,
        session_id: str,
        *,
        runtime_id: str | None = None,
        reason: str,
        coalesce_ms: int = 300,
    ) -> dict[str, Any] | None:
        wrapper = _runtime_wrapper(self.runtime, "_publish_session_transport_invalidate")
        if wrapper is not None:
            return wrapper(
                session_id,
                runtime_id=runtime_id,
                reason=reason,
                coalesce_ms=coalesce_ms,
            )
        return publish_session_transport_invalidate(
            self.runtime.event_hub,
            self.runtime.api.clean_optional_text,
            session_id,
            runtime_id=runtime_id,
            reason=reason,
            coalesce_ms=coalesce_ms,
        )


def service(runtime: ServerRuntime) -> EventPublishService:
    return EventPublishService(runtime)


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
