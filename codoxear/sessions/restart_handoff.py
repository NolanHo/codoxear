from __future__ import annotations

from typing import Any

from ..agent_backend import normalize_agent_backend
from .runtime_access import manager_runtime


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip()
    return out or None


def _listed_session_row(manager: Any, session_id: str) -> dict[str, Any] | None:
    for row in manager.list_sessions():
        if str(row.get("session_id") or "") == session_id:
            return dict(row)
    return None


def restart_session(manager: Any, session_id: str) -> dict[str, Any]:
    runtime_id = manager.runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        listed_row = _listed_session_row(manager, session_id)
        if isinstance(listed_row, dict) and listed_row.get("pending_startup"):
            raise ValueError("session is still starting")
        raise KeyError("unknown session")
    source = manager.get_session(runtime_id)
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

    sv = manager_runtime(manager)
    durable_session_id = manager.durable_session_id_for_session(source)
    ref = ("pi", durable_session_id)
    create_in_tmux = (source.transport or "").strip().lower() == "tmux"
    preserved_state = manager.capture_runtime_bound_restart_state(runtime_id, ref)
    db = getattr(manager, "_page_state_db", None)
    restore_record = (
        db.load_sessions().get(ref) if isinstance(db, sv.api.PageStateDB) else None
    )
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
    manager.persist_durable_session_record(
        sv.api.DurableSessionRecord(
            backend="pi",
            session_id=durable_session_id,
            cwd=restore_record.cwd or cwd,
            source_path=restore_record.source_path or str(source_path),
            title=restore_record.title,
            first_user_message=restore_record.first_user_message,
            created_at=restore_record.created_at,
            updated_at=max(
                restore_record.updated_at,
                sv.api.safe_path_mtime(source_path),
            ),
            pending_startup=True,
        )
    )
    manager.stage_runtime_bound_restart_state(runtime_id, ref, preserved_state)
    if not manager.kill_session(runtime_id):
        manager.restore_runtime_bound_restart_state(runtime_id, ref, preserved_state)
        manager.persist_durable_session_record(restore_record)
        raise RuntimeError("failed to stop source session for restart")
    manager.discard_runtime_session(
        runtime_id,
        sock_path=source.sock_path,
        clear_state=False,
    )
    sv.api.event_publish.service(sv).publish_sessions_invalidate(reason="session_created")

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
        manager.persist_durable_session_record(restore_record)
        sv.api.event_publish.service(sv).publish_sessions_invalidate(reason="session_created")
        raise

    payload = dict(spawn_res)
    payload["session_id"] = durable_session_id
    payload["backend"] = "pi"
    payload["previous_runtime_id"] = runtime_id
    launched_runtime_id = _clean_optional_text(payload.get("runtime_id"))
    if launched_runtime_id is not None:
        manager.restore_runtime_bound_restart_state(
            launched_runtime_id,
            ref,
            preserved_state,
        )
        manager.persist_durable_session_record(
            sv.api.DurableSessionRecord(
                backend="pi",
                session_id=durable_session_id,
                cwd=restore_record.cwd or cwd,
                source_path=restore_record.source_path or str(source_path),
                title=restore_record.title,
                first_user_message=restore_record.first_user_message,
                created_at=restore_record.created_at,
                updated_at=max(
                    restore_record.updated_at,
                    sv.api.safe_path_mtime(source_path),
                ),
                pending_startup=False,
            )
        )
    else:
        sv.api.threading.Thread(
            target=manager.finalize_pending_pi_restart_state,
            kwargs={
                "durable_session_id": durable_session_id,
                "ref": ref,
                "state": preserved_state,
            },
            daemon=True,
        ).start()
    return payload


def handoff_session(manager: Any, session_id: str) -> dict[str, Any]:
    runtime_id = manager.runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        listed_row = _listed_session_row(manager, session_id)
        if isinstance(listed_row, dict) and listed_row.get("pending_startup"):
            raise ValueError("session is still starting")
        raise KeyError("unknown session")
    source = manager.get_session(runtime_id)
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

    sv = manager_runtime(manager)
    source_session_id = manager.durable_session_id_for_session(source)
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
        launched_session_id = (
            _clean_optional_text(spawn_res.get("session_id")) or new_session_id
        )
        launched = manager.wait_for_live_session(launched_session_id)
        launched_runtime_id = launched.session_id
        alias = manager.copy_session_ui_identity(
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
