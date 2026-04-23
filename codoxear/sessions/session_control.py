from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..agent_backend import normalize_agent_backend
from . import spawn_flow as _spawn_flow
from . import restart_handoff as _restart_handoff


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


def _historical_session_row(manager: Any, session_id: str) -> dict[str, Any] | None:
    parsed = _parse_historical_session_id(session_id)
    if parsed is None:
        return None
    backend, resume_session_id = parsed
    for row in manager.list_sessions():
        if normalize_agent_backend(row.get("agent_backend", row.get("backend")), default="codex") != backend:
            continue
        if _clean_optional_text(row.get("resume_session_id")) != resume_session_id:
            continue
        out = dict(row)
        out["session_id"] = session_id
        out["resume_session_id"] = resume_session_id
        out["historical"] = True
        return out
    return None


def _listed_session_row(manager: Any, session_id: str) -> dict[str, Any] | None:
    for row in manager.list_sessions():
        if str(row.get("session_id") or "") == session_id:
            return dict(row)
    return None


def _resume_historical_pi_session(manager: Any, session_id: str) -> dict[str, Any] | None:
    historical_row = _historical_session_row(manager, session_id)
    if historical_row is None and manager._runtime_session_id_for_identifier(session_id) is None:
        listed_row = _listed_session_row(manager, session_id)
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
    cwd = _clean_optional_text(historical_row.get("cwd"))
    resume_session_id = _clean_optional_text(historical_row.get("resume_session_id"))
    if cwd is None or resume_session_id is None:
        raise ValueError("historical session is missing resume metadata")
    spawn_res = manager.spawn_web_session(
        cwd=cwd,
        backend="pi",
        resume_session_id=resume_session_id,
    )
    manager._discover_existing(force=True, skip_invalid_sidecars=True)
    live_runtime_id = _clean_optional_text(spawn_res.get("runtime_id"))
    live_session_id = _clean_optional_text(spawn_res.get("session_id"))
    if live_runtime_id is None or live_session_id is None:
        raise RuntimeError("spawned session did not return session identities")
    if manager._runtime_session_id_for_identifier(live_runtime_id) is None:
        raise RuntimeError("spawned session is not yet discoverable")
    return {
        "runtime_id": live_runtime_id,
        "session_id": live_session_id,
        "backend": "pi",
    }


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


@dataclass(slots=True)
class SessionControlService:
    manager: Any

    def send(self, session_id: str, text: str) -> dict[str, Any]:
        return send(self.manager, session_id, text)

    def enqueue(self, session_id: str, text: str) -> dict[str, Any]:
        return enqueue(self.manager, session_id, text)

    def queue_list(self, session_id: str) -> list[str]:
        return queue_list(self.manager, session_id)

    def queue_delete(self, session_id: str, index: int) -> dict[str, Any]:
        return queue_delete(self.manager, session_id, int(index))

    def queue_update(self, session_id: str, index: int, text: str) -> dict[str, Any]:
        return queue_update(self.manager, session_id, int(index), text)

    def spawn_web_session(
        self,
        *,
        cwd: str,
        args: list[str] | None = None,
        agent_backend: str = "codex",
        resume_session_id: str | None = None,
        worktree_branch: str | None = None,
        model_provider: str | None = None,
        preferred_auth_method: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        service_tier: str | None = None,
        create_in_tmux: bool = False,
        backend: str | None = None,
    ) -> dict[str, Any]:
        return spawn_web_session(
            self.manager,
            cwd=cwd,
            args=args,
            agent_backend=agent_backend,
            resume_session_id=resume_session_id,
            worktree_branch=worktree_branch,
            model_provider=model_provider,
            preferred_auth_method=preferred_auth_method,
            model=model,
            reasoning_effort=reasoning_effort,
            service_tier=service_tier,
            create_in_tmux=create_in_tmux,
            backend=backend,
        )

    def restart_session(self, session_id: str) -> dict[str, Any]:
        return restart_session(self.manager, session_id)

    def handoff_session(self, session_id: str) -> dict[str, Any]:
        return handoff_session(self.manager, session_id)


def service(manager: Any) -> SessionControlService:
    return SessionControlService(manager)


def send(manager: Any, session_id: str, text: str) -> dict[str, Any]:
    resumed = _resume_historical_pi_session(manager, session_id)
    if resumed is not None:
        resp = send(manager, resumed["runtime_id"], text)
        out = dict(resp)
        out["session_id"] = resumed["session_id"]
        out["runtime_id"] = resumed["runtime_id"]
        out["backend"] = resumed["backend"]
        return out

    runtime_id = manager._runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        raise KeyError("unknown session")
    with manager._lock:
        session = manager._sessions.get(runtime_id)
        if not session:
            raise KeyError("unknown session")
        durable_session_id = manager._durable_session_id_for_session(session)
    transport_state, transport_error = manager._probe_bridge_transport(runtime_id)
    if transport_state == "dead":
        with manager._lock:
            manager._sessions.pop(runtime_id, None)
        manager._clear_deleted_session_state(runtime_id)
        _unlink_quiet(session.sock_path)
        _unlink_quiet(session.sock_path.with_suffix(".json"))
        raise KeyError("unknown session")
    request = manager._enqueue_outbound_request(runtime_id, text)
    return {
        "ok": True,
        "accepted": True,
        "request_id": request.request_id,
        "delivery_state": request.state,
        "session_id": durable_session_id,
        "runtime_id": runtime_id,
        "backend": session.backend,
        "transport_state": transport_state,
        "transport_error": transport_error,
    }


def enqueue(manager: Any, session_id: str, text: str) -> dict[str, Any]:
    resumed = _resume_historical_pi_session(manager, session_id)
    if resumed is not None:
        resp = enqueue(manager, resumed["runtime_id"], text)
        out = dict(resp)
        out["session_id"] = resumed["session_id"]
        out["runtime_id"] = resumed["runtime_id"]
        out["backend"] = resumed["backend"]
        return out
    return manager._queue_enqueue_local(session_id, text)


def queue_list(manager: Any, session_id: str) -> list[str]:
    runtime_id = manager._runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        raise KeyError("unknown session")
    return manager._queue_list_local(runtime_id)


def queue_delete(manager: Any, session_id: str, index: int) -> dict[str, Any]:
    return manager._queue_delete_local(session_id, int(index))


def queue_update(manager: Any, session_id: str, index: int, text: str) -> dict[str, Any]:
    return manager._queue_update_local(session_id, int(index), text)


def spawn_web_session(
    manager: Any,
    *,
    cwd: str,
    args: list[str] | None = None,
    agent_backend: str = "codex",
    resume_session_id: str | None = None,
    worktree_branch: str | None = None,
    model_provider: str | None = None,
    preferred_auth_method: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
    create_in_tmux: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    return _spawn_flow.spawn_web_session(
        manager,
        cwd=cwd,
        args=args,
        agent_backend=agent_backend,
        resume_session_id=resume_session_id,
        worktree_branch=worktree_branch,
        model_provider=model_provider,
        preferred_auth_method=preferred_auth_method,
        model=model,
        reasoning_effort=reasoning_effort,
        service_tier=service_tier,
        create_in_tmux=create_in_tmux,
        backend=backend,
    )


def restart_session(manager: Any, session_id: str) -> dict[str, Any]:
    return _restart_handoff.restart_session(manager, session_id)


def handoff_session(manager: Any, session_id: str) -> dict[str, Any]:
    return _restart_handoff.handoff_session(manager, session_id)
