from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..runtime import ServerRuntime


def _session_path_cache_key(session: Any) -> str | None:
    return str(session.session_path.resolve()) if isinstance(session.session_path, Path) else None


def _discard_dead_bridge_session(
    runtime: ServerRuntime,
    manager: Any,
    *,
    runtime_id: str,
    session: Any,
) -> None:
    runtime.api.unlink_quiet(session.sock_path)
    runtime.api.unlink_quiet(session.sock_path.with_suffix(".json"))
    manager.discard_runtime_session(runtime_id, sock_path=None)


def _broker_unavailable_error(
    runtime: ServerRuntime,
    manager: Any,
    *,
    runtime_id: str,
    session: Any,
) -> ValueError:
    if (not runtime.api.pid_alive(session.broker_pid)) and (not runtime.api.pid_alive(session.codex_pid)):
        _discard_dead_bridge_session(runtime, manager, runtime_id=runtime_id, session=session)
        raise KeyError("unknown session")
    return ValueError("broker unavailable")


def get_ui_state(runtime: ServerRuntime, manager: Any, session_id: str) -> dict[str, Any]:
    runtime_id, session = manager.resolve_pi_bridge_session(
        session_id,
        unsupported_message="ui interactions are only supported for pi sessions",
    )
    try:
        resp = manager.sock_call(session.sock_path, {"cmd": "ui_state"}, timeout_s=1.5)
    except Exception:
        raise _broker_unavailable_error(
            runtime,
            manager,
            runtime_id=runtime_id,
            session=session,
        )
    if resp.get("error") == "unknown cmd":
        if runtime.api.session_display.service(runtime).session_supports_live_pi_ui(session):
            raise ValueError("live ui interactions are unavailable for this pi session")
        return {"requests": []}
    error = resp.get("error")
    if isinstance(error, str) and error:
        raise ValueError(error)
    return dict(runtime.api.sanitize_pi_ui_state_payload(resp))



def get_session_commands(runtime: ServerRuntime, manager: Any, session_id: str) -> dict[str, Any]:
    runtime_id, session = manager.resolve_pi_bridge_session(
        session_id,
        unsupported_message="command listing is only supported for pi sessions",
    )
    now_ts = time.time()
    session_path_key = _session_path_cache_key(session)
    cached = manager.pi_commands_cache_get(
        runtime_id,
        thread_id=session.thread_id,
        session_path_key=session_path_key,
        now_ts=now_ts,
    )
    if cached is not None:
        return {"commands": cached}
    try:
        resp = manager.sock_call(session.sock_path, {"cmd": "commands"}, timeout_s=2.0)
    except Exception:
        raise _broker_unavailable_error(
            runtime,
            manager,
            runtime_id=runtime_id,
            session=session,
        )
    if resp.get("error") == "unknown cmd":
        return {"commands": []}
    error = resp.get("error")
    if isinstance(error, str) and error:
        raise ValueError(error)
    payload = runtime.api.sanitize_pi_commands_payload(resp)
    manager.pi_commands_cache_put(
        runtime_id,
        thread_id=session.thread_id,
        session_path_key=session_path_key,
        commands=list(payload.get("commands", [])),
        now_ts=now_ts,
    )
    return dict(payload)



def submit_ui_response(runtime: ServerRuntime, manager: Any, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    runtime_id, session = manager.resolve_pi_bridge_session(
        session_id,
        unsupported_message="ui interactions are only supported for pi sessions",
    )
    forward: dict[str, Any] = {"cmd": "ui_response"}
    for key in ("id", "value", "confirmed", "cancelled"):
        if key in payload:
            forward[key] = payload[key]
    try:
        resp = manager.sock_call(session.sock_path, forward, timeout_s=3.0)
    except Exception:
        raise _broker_unavailable_error(
            runtime,
            manager,
            runtime_id=runtime_id,
            session=session,
        )
    if resp.get("error") == "unknown cmd":
        if runtime.api.session_display.service(runtime).session_supports_live_pi_ui(session):
            raise ValueError("live ui responses are unavailable for this pi session")
        if payload.get("cancelled") is True:
            manager.inject_keys(runtime_id, "\\x1b")
            return {"ok": True, "legacy_fallback": True}
        text = runtime.api.legacy_pi_ui_response_text(payload)
        if text is None:
            raise ValueError("ui response value required")
        manager.send(runtime_id, text)
        return {"ok": True, "legacy_fallback": True}
    error = resp.get("error")
    if isinstance(error, str) and error:
        raise ValueError(error)
    return dict(resp)
