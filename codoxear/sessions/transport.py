from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..agents import get_agent_adapter
from .runtime_access import manager_runtime


def _runtime(manager: Any):
    return manager_runtime(manager)


def _live_session(manager: Any, session_id: str) -> tuple[str, Any]:
    runtime_id = manager.runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        raise KeyError("unknown session")
    session = manager.get_session(runtime_id)
    if session is None:
        raise KeyError("unknown session")
    return runtime_id, session


def _discard_dead_runtime(
    manager: Any,
    runtime_id: str,
    sock_path: Path,
    *,
    clear_state: bool,
) -> None:
    manager.discard_runtime_session(
        runtime_id,
        sock_path=sock_path,
        clear_state=clear_state,
    )


@dataclass(slots=True)
class SessionTransportService:
    manager: Any

    def sock_call(
        self, sock_path: Path, req: dict[str, Any], timeout_s: float = 2.0
    ) -> dict[str, Any]:
        return sock_call(self.manager, sock_path, req, timeout_s=timeout_s)

    def kill_session_via_pids(self, session: Any) -> bool:
        return kill_session_via_pids(self.manager, session)

    def kill_session(self, session_id: str) -> bool:
        return kill_session(self.manager, session_id)

    def get_state(self, session_id: str) -> dict[str, Any]:
        return get_state(self.manager, session_id)

    def get_tail(self, session_id: str) -> str:
        return get_tail(self.manager, session_id)

    def inject_keys(self, session_id: str, seq: str) -> dict[str, Any]:
        return inject_keys(self.manager, session_id, seq)


def service(manager: Any) -> SessionTransportService:
    return SessionTransportService(manager)


def sock_call(
    manager: Any, sock_path: Path, req: dict[str, Any], timeout_s: float = 2.0
) -> dict[str, Any]:
    manager_dict = getattr(manager, "__dict__", None)
    override = manager_dict.get("_sock_call") if isinstance(manager_dict, dict) else None
    if callable(override):
        return override(sock_path, req, timeout_s=timeout_s)
    adapter = get_agent_adapter(None)
    return adapter.sock_call(sock_path, req, timeout_s=timeout_s)


def kill_session_via_pids(manager: Any, session: Any) -> bool:
    sv = _runtime(manager)
    group_alive = sv.api.process_group_alive(int(session.codex_pid))
    broker_alive = sv.api.pid_alive(int(session.broker_pid))
    if not group_alive and not broker_alive:
        sv.api.unlink_quiet(session.sock_path)
        sv.api.unlink_quiet(session.sock_path.with_suffix(".json"))
        return True
    if group_alive and (
        not sv.api.terminate_process_group(int(session.codex_pid), wait_seconds=1.0)
    ):
        return False
    if sv.api.pid_alive(int(session.broker_pid)) and (
        not sv.api.terminate_process(int(session.broker_pid), wait_seconds=1.0)
    ):
        return False
    group_dead = not sv.api.process_group_alive(int(session.codex_pid))
    broker_dead = not sv.api.pid_alive(int(session.broker_pid))
    if group_dead and broker_dead:
        sv.api.unlink_quiet(session.sock_path)
        sv.api.unlink_quiet(session.sock_path.with_suffix(".json"))
        return True
    return False


def kill_session(manager: Any, session_id: str) -> bool:
    runtime_id = manager.runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        return False
    session = manager.get_session(runtime_id)
    if session is None:
        return False
    try:
        resp = sock_call(manager, session.sock_path, {"cmd": "shutdown"}, timeout_s=1.0)
    except Exception:
        return manager.kill_session_via_pids(session)
    if resp.get("ok") is True:
        return True
    return manager.kill_session_via_pids(session)


def get_state(manager: Any, session_id: str) -> dict[str, Any]:
    sv = _runtime(manager)
    runtime_id, session = _live_session(manager, session_id)
    sock = session.sock_path
    cached_state = {
        "busy": bool(session.busy),
        "queue_len": int(session.queue_len),
        "token": session.token,
    }
    try:
        resp = sock_call(manager, sock, {"cmd": "state"}, timeout_s=1.5)
        sv.api.session_display.service(sv).validated_session_state(resp)
    except Exception:
        if not sv.api.pid_alive(session.broker_pid) and not sv.api.pid_alive(session.codex_pid):
            _discard_dead_runtime(manager, runtime_id, sock, clear_state=True)
            raise KeyError("unknown session")
        return cached_state
    session2 = manager.get_session(runtime_id)
    if session2 is not None:
        session2.busy = sv.api.session_display.service(sv).state_busy_value(resp)
        session2.queue_len = sv.api.session_display.service(sv).state_queue_len_value(resp)
        if "token" in resp:
            tok = resp.get("token")
            if isinstance(tok, dict):
                session2.token = tok
        return resp
    return cached_state


def get_tail(manager: Any, session_id: str) -> str:
    sv = _runtime(manager)
    runtime_id, session = _live_session(manager, session_id)
    sock = session.sock_path
    try:
        resp = sock_call(manager, sock, {"cmd": "tail"}, timeout_s=1.5)
    except Exception:
        if not sv.api.pid_alive(session.broker_pid) and not sv.api.pid_alive(session.codex_pid):
            _discard_dead_runtime(manager, runtime_id, sock, clear_state=False)
            raise KeyError("unknown session")
        raise
    if "tail" not in resp:
        raise ValueError("invalid broker tail response")
    tail = resp.get("tail")
    if not isinstance(tail, str):
        raise ValueError("invalid broker tail response")
    return tail


def inject_keys(manager: Any, session_id: str, seq: str) -> dict[str, Any]:
    sv = _runtime(manager)
    runtime_id, session = _live_session(manager, session_id)
    sock = session.sock_path
    try:
        resp = sock_call(manager, sock, {"cmd": "keys", "seq": seq}, timeout_s=2.0)
    except Exception:
        if not sv.api.pid_alive(session.broker_pid) and not sv.api.pid_alive(session.codex_pid):
            _discard_dead_runtime(manager, runtime_id, sock, clear_state=False)
            raise KeyError("unknown session")
        raise
    err = resp.get("error")
    if isinstance(err, str) and err:
        raise ValueError(err)
    return resp
