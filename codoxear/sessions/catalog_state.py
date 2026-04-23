from __future__ import annotations

from pathlib import Path
from typing import Any


def refresh_session_state(
    manager: Any,
    session_id: str,
    sock_path: Path,
    timeout_s: float = 0.4,
) -> tuple[bool, BaseException | None]:
    sv = manager._runtime
    try:
        resp = manager._sock_call(sock_path, {"cmd": "state"}, timeout_s=timeout_s)
        sv.api.validated_session_state(resp)
    except Exception as exc:
        return False, exc

    publish_sessions = False
    publish_live = False
    publish_workspace = False
    durable_session_id: str | None = None
    with manager._lock:
        session = manager._sessions.get(session_id)
        if session:
            next_busy = sv.api.state_busy_value(resp)
            next_queue_len = sv.api.state_queue_len_value(resp)
            next_token = resp.get("token") if isinstance(resp.get("token"), dict) else session.token
            durable_session_id = manager._durable_session_id_for_session(session)
            publish_sessions = session.busy != next_busy
            publish_live = publish_sessions or session.queue_len != next_queue_len or next_token != session.token
            publish_workspace = session.queue_len != next_queue_len
            session.busy = next_busy
            session.queue_len = next_queue_len
            if isinstance(resp.get("token"), dict):
                session.token = resp.get("token")

    if durable_session_id is not None:
        if publish_sessions:
            sv.api.publish_sessions_invalidate(reason="session_state_changed")
        if publish_live:
            sv.api.publish_session_live_invalidate(
                durable_session_id,
                runtime_id=session_id,
                reason="session_state_changed",
            )
        if publish_workspace:
            sv.api.publish_session_workspace_invalidate(
                durable_session_id,
                runtime_id=session_id,
                reason="session_state_changed",
            )

    return True, None


def prune_dead_sessions(manager: Any) -> None:
    sv = manager._runtime
    with manager._lock:
        items = list(manager._sessions.items())

    dead: list[tuple[str, Path]] = []
    for sid, session in items:
        if not session.sock_path.exists():
            dead.append((sid, session.sock_path))
            continue
        ok, _ = refresh_session_state(manager, sid, session.sock_path, timeout_s=0.4)
        if ok:
            continue
        if not sv.api.probe_failure_safe_to_prune(
            broker_pid=session.broker_pid,
            codex_pid=session.codex_pid,
        ):
            continue
        dead.append((sid, session.sock_path))

    if not dead:
        return

    dead_events: list[tuple[str, str]] = []
    with manager._lock:
        for sid, _sock in dead:
            session = manager._sessions.pop(sid, None)
            if session is not None:
                dead_events.append((manager._durable_session_id_for_session(session), sid))

    for sid, sock in dead:
        manager._clear_deleted_session_state(sid)
        sv.api.unlink_quiet(sock)
        sv.api.unlink_quiet(sock.with_suffix(".json"))

    sv.api.publish_sessions_invalidate(reason="session_removed")
    for durable_session_id, runtime_id in dead_events:
        sv.api.publish_session_live_invalidate(
            durable_session_id,
            runtime_id=runtime_id,
            reason="session_removed",
        )
        sv.api.publish_session_workspace_invalidate(
            durable_session_id,
            runtime_id=runtime_id,
            reason="session_removed",
        )
