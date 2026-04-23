from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..agent_backend import normalize_agent_backend
from . import spawn_flow as _spawn_flow


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
    runtime_id = manager._runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        listed_row = _listed_session_row(manager, session_id)
        if isinstance(listed_row, dict) and listed_row.get("pending_startup"):
            raise ValueError("session is still starting")
        raise KeyError("unknown session")
    with manager._lock:
        source = manager._sessions.get(runtime_id)
    if source is None:
        raise KeyError("unknown session")
    if normalize_agent_backend(source.backend, default=source.agent_backend) != "pi":
        raise ValueError("restart is only supported for pi sessions")
    source_path = source.session_path
    if source_path is None or (not source_path.exists()):
        raise ValueError("pi session file not found")
    cwd = _clean_optional_text(source.cwd)
    if cwd is None:
        raise ValueError("session is missing cwd")

    sv = manager._runtime
    durable_session_id = manager._durable_session_id_for_session(source)
    ref = ("pi", durable_session_id)
    create_in_tmux = (source.transport or "").strip().lower() == "tmux"
    preserved_state = manager._capture_runtime_bound_restart_state(runtime_id, ref)
    db = getattr(manager, "_page_state_db", None)
    restore_record = db.load_sessions().get(ref) if isinstance(db, sv.api.PageStateDB) else None
    if restore_record is None:
        restore_record = sv.api.DurableSessionRecord(
            backend="pi",
            session_id=durable_session_id,
            cwd=cwd,
            source_path=str(source_path),
            title=source.title,
            first_user_message=source.first_user_message,
            created_at=sv.api.safe_path_mtime(source_path),
            updated_at=sv.api.safe_path_mtime(source_path),
            pending_startup=False,
        )
    manager._persist_durable_session_record(
        sv.api.DurableSessionRecord(
            backend="pi",
            session_id=durable_session_id,
            cwd=restore_record.cwd or cwd,
            source_path=restore_record.source_path or str(source_path),
            title=restore_record.title,
            first_user_message=restore_record.first_user_message,
            created_at=restore_record.created_at,
            updated_at=max(restore_record.updated_at, sv.api.safe_path_mtime(source_path)),
            pending_startup=True,
        )
    )
    manager._stage_runtime_bound_restart_state(runtime_id, ref, preserved_state)
    if not manager.kill_session(runtime_id):
        manager._restore_runtime_bound_restart_state(runtime_id, ref, preserved_state)
        manager._persist_durable_session_record(restore_record)
        raise RuntimeError("failed to stop source session for restart")
    sv.api.unlink_quiet(source.sock_path)
    sv.api.unlink_quiet(source.sock_path.with_suffix(".json"))
    with manager._lock:
        manager._sessions.pop(runtime_id, None)
    sv.api.publish_sessions_invalidate(reason="session_created")

    provider = _clean_optional_text(source.model_provider)
    model_id = _clean_optional_text(source.model)
    thinking_level = _clean_optional_text(source.reasoning_effort)
    try:
        spawn_res = manager.spawn_web_session(
            cwd=cwd,
            backend="pi",
            resume_session_id=durable_session_id,
            model_provider=provider,
            model=model_id,
            reasoning_effort=thinking_level,
            create_in_tmux=create_in_tmux,
        )
    except Exception:
        manager._persist_durable_session_record(restore_record)
        sv.api.publish_sessions_invalidate(reason="session_created")
        raise

    payload = dict(spawn_res)
    payload["session_id"] = durable_session_id
    payload["backend"] = "pi"
    payload["previous_runtime_id"] = runtime_id
    launched_runtime_id = _clean_optional_text(payload.get("runtime_id"))
    if launched_runtime_id is not None:
        manager._restore_runtime_bound_restart_state(launched_runtime_id, ref, preserved_state)
        manager._persist_durable_session_record(
            sv.api.DurableSessionRecord(
                backend="pi",
                session_id=durable_session_id,
                cwd=restore_record.cwd or cwd,
                source_path=restore_record.source_path or str(source_path),
                title=restore_record.title,
                first_user_message=restore_record.first_user_message,
                created_at=restore_record.created_at,
                updated_at=max(restore_record.updated_at, sv.api.safe_path_mtime(source_path)),
                pending_startup=False,
            )
        )
    else:
        sv.api.threading.Thread(
            target=manager._finalize_pending_pi_restart_state,
            kwargs={
                "durable_session_id": durable_session_id,
                "ref": ref,
                "state": preserved_state,
            },
            daemon=True,
        ).start()
    return payload


def handoff_session(manager: Any, session_id: str) -> dict[str, Any]:
    runtime_id = manager._runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        listed_row = _listed_session_row(manager, session_id)
        if isinstance(listed_row, dict) and listed_row.get("pending_startup"):
            raise ValueError("session is still starting")
        raise KeyError("unknown session")
    with manager._lock:
        source = manager._sessions.get(runtime_id)
    if source is None:
        raise KeyError("unknown session")
    if normalize_agent_backend(source.backend, default=source.agent_backend) != "pi":
        raise ValueError("handoff is only supported for pi sessions")
    source_path = source.session_path
    if source_path is None or (not source_path.exists()):
        raise ValueError("pi session file not found")
    cwd = _clean_optional_text(source.cwd)
    if cwd is None:
        raise ValueError("session is missing cwd")

    sv = manager._runtime
    source_session_id = manager._durable_session_id_for_session(source)
    history_path = sv.api.next_pi_handoff_history_path(source_path)
    new_session_id = str(sv.api.uuid.uuid4())
    new_session_path = sv.api.pi_new_session_file_for_cwd(cwd)
    provider, model_id, thinking_level = sv.api.read_pi_run_settings(source_path)
    provider = _clean_optional_text(source.model_provider) or provider
    model_id = _clean_optional_text(source.model) or model_id
    thinking_level = _clean_optional_text(source.reasoning_effort) or thinking_level
    create_in_tmux = (source.transport or "").strip().lower() == "tmux"
    copied_history = False
    launched_session_id = new_session_id
    launched_runtime_id: str | None = None
    try:
        sv.api.copy_file_atomic(source_path, history_path)
        copied_history = True
        sv.api.pi_session_files.service(sv).write_pi_handoff_session(
            new_session_path,
            session_id=new_session_id,
            cwd=cwd,
            source_session_id=source_session_id,
            history_path=history_path,
            provider=provider,
            model_id=model_id,
            thinking_level=thinking_level,
        )
        spawn_res = manager.spawn_web_session(
            cwd=cwd,
            backend="pi",
            resume_session_id=new_session_id,
            model_provider=provider,
            model=model_id,
            reasoning_effort=thinking_level,
            create_in_tmux=create_in_tmux,
        )
        launched_session_id = _clean_optional_text(spawn_res.get("session_id")) or new_session_id
        launched = manager._wait_for_live_session(launched_session_id)
        launched_runtime_id = launched.session_id
        alias = manager._copy_session_ui_identity(
            source_session_id=session_id,
            target_session_id=launched_session_id,
        )
        if not manager.delete_session(runtime_id):
            raise RuntimeError("failed to stop source session after handoff launch")
        payload = dict(spawn_res)
        payload["session_id"] = launched_session_id
        payload["runtime_id"] = launched_runtime_id
        payload["backend"] = "pi"
        payload["history_path"] = str(history_path)
        payload["previous_session_id"] = source_session_id
        if alias:
            payload["alias"] = alias
        return payload
    except Exception:
        if launched_runtime_id is not None:
            try:
                manager.delete_session(launched_runtime_id)
            except Exception:
                pass
        else:
            try:
                manager.delete_session(launched_session_id)
            except Exception:
                pass
        sv.api.unlink_quiet(new_session_path)
        if copied_history:
            sv.api.unlink_quiet(history_path)
        raise
