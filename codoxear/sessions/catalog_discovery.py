from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..agent_backend import normalize_agent_backend
from .runtime_access import manager_runtime


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip()
    return out or None


def _discover_one_socket(
    manager: Any,
    sv: Any,
    sock: Path,
    *,
    skip_invalid_sidecars: bool,
) -> None:
    session_id = sock.stem
    try:
        meta_path = sock.with_suffix(".json")
        if not meta_path.exists():
            return
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            raise ValueError(f"invalid metadata json for socket {sock}")

        thread_id = _clean_optional_text(meta.get("session_id")) or session_id
        backend = normalize_agent_backend(
            meta.get("backend"),
            default=normalize_agent_backend(meta.get("agent_backend"), default="codex"),
        )
        agent_backend = normalize_agent_backend(meta.get("agent_backend"), default=backend)
        codex_pid_raw = meta.get("codex_pid")
        broker_pid_raw = meta.get("broker_pid")
        if not isinstance(codex_pid_raw, int):
            raise ValueError(f"invalid codex_pid in metadata for socket {sock}")
        if not isinstance(broker_pid_raw, int):
            raise ValueError(f"invalid broker_pid in metadata for socket {sock}")
        codex_pid = int(codex_pid_raw)
        broker_pid = int(broker_pid_raw)
        owned = (meta.get("owner") == "web") if isinstance(meta.get("owner"), str) else False
        transport, tmux_session, tmux_window = manager.session_transport(meta=meta)
        supports_live_ui = meta.get("supports_live_ui") if isinstance(meta.get("supports_live_ui"), bool) else None
        ui_protocol_version_raw = meta.get("ui_protocol_version")
        ui_protocol_version = ui_protocol_version_raw if type(ui_protocol_version_raw) is int else None
        if backend == "pi" and transport is None and (owned or sv.api.supports_web_control(meta)):
            transport = "pi-rpc"
        if backend == "pi" and transport == "pi-rpc" and supports_live_ui is None:
            supports_live_ui = True
        if backend == "pi" and transport == "pi-rpc" and supports_live_ui is True and ui_protocol_version is None:
            ui_protocol_version = 1

        cwd_raw = meta.get("cwd")
        if not isinstance(cwd_raw, str) or (not cwd_raw.strip()):
            raise ValueError(f"invalid cwd in metadata for socket {sock}")
        cwd = cwd_raw

        start_ts_raw = meta.get("start_ts")
        if not isinstance(start_ts_raw, (int, float)):
            raise ValueError(f"invalid start_ts in metadata for socket {sock}")
        start_ts = float(start_ts_raw)

        session_path_discovered = False
        inferred_pi_session_path: Path | None = None
        if backend == "codex" and agent_backend == "codex":
            for key in ("session_path", "log_path"):
                raw_path = meta.get(key)
                if not isinstance(raw_path, str) or not raw_path.strip():
                    continue
                candidate = Path(raw_path)
                if sv.api.infer_agent_backend_from_log_path(candidate) != "pi":
                    continue
                inferred_pi_session_path = candidate
                break
            if inferred_pi_session_path is None and sv.api.pid_alive(codex_pid):
                ignored_paths = manager.claimed_pi_session_paths(exclude_sid=session_id)
                inferred_pi_session_path = sv.api.proc_find_open_rollout_log(
                    proc_root=sv.api.PROC_ROOT,
                    root_pid=codex_pid,
                    agent_backend="pi",
                    cwd=cwd,
                    ignored_paths=ignored_paths,
                )
        if inferred_pi_session_path is not None:
            backend = "pi"
            agent_backend = "pi"
            session_path_discovered = True
            if transport is None and (owned or sv.api.supports_web_control(meta)):
                transport = "pi-rpc"
            if supports_live_ui is None and transport == "pi-rpc":
                supports_live_ui = True
            if ui_protocol_version is None and supports_live_ui is True:
                ui_protocol_version = 1
            sv.api.patch_metadata_pi_binding(sock, inferred_pi_session_path)

        if backend == "pi":
            if transport != "pi-rpc":
                return
            if supports_live_ui is not True:
                return
            if not isinstance(ui_protocol_version, int) or ui_protocol_version < 1:
                return
            if (not owned) and (not sv.api.supports_web_control(meta)):
                return

        log_path = sv.api.session_settings.service(sv).metadata_log_path(meta=meta, backend=backend, sock=sock)
        if inferred_pi_session_path is not None:
            session_path = inferred_pi_session_path
        else:
            preferred_session_path: Path | None = None
            if backend == "pi":
                try:
                    preferred_session_path = sv.api.session_settings.service(sv).metadata_session_path(meta=meta, backend=backend, sock=sock)
                except ValueError as exc:
                    if "missing session_path" not in str(exc):
                        raise
                claimed: set[Path] | None = (
                    manager.claimed_pi_session_paths(exclude_sid=session_id)
                    if preferred_session_path is None
                    else None
                )
                session_path, session_path_source = sv.api.resolve_pi_session_path(
                    thread_id=thread_id,
                    cwd=cwd,
                    start_ts=start_ts,
                    preferred=preferred_session_path,
                    exclude=claimed,
                )
                if session_path is not None and session_path_source in {"exact", "discovered"}:
                    session_path_discovered = True
                    sv.api.patch_metadata_session_path(
                        sock,
                        session_path,
                        force=preferred_session_path is not None and preferred_session_path != session_path,
                    )
            else:
                session_path = sv.api.session_settings.service(sv).metadata_session_path(meta=meta, backend=backend, sock=sock)
        if log_path is not None and log_path.exists():
            thread_id, log_path = sv.api.coerce_main_thread_log(thread_id=thread_id, log_path=log_path)
        else:
            log_path = None
    except Exception as exc:
        if skip_invalid_sidecars:
            manager.quarantine_sidecar(sock, exc, log=False)
            return
        raise
    manager.clear_sidecar_quarantine(sock)

    if (log_path is None) and (not sv.api.pid_alive(codex_pid)) and (not sv.api.pid_alive(broker_pid)):
        manager.unhide_session(session_id)
        sv.api.unlink_quiet(sock)
        sv.api.unlink_quiet(meta_path)
        return

    resume_session_id = _clean_optional_text(meta.get("resume_session_id"))
    if manager.session_is_hidden(session_id, thread_id, resume_session_id, agent_backend):
        if (not sv.api.pid_alive(codex_pid)) and (not sv.api.pid_alive(broker_pid)):
            manager.unhide_session(session_id)
            sv.api.unlink_quiet(sock)
            sv.api.unlink_quiet(meta_path)
        return

    try:
        model_provider, preferred_auth_method, model, reasoning_effort = manager.session_run_settings(
            backend=backend, meta=meta, log_path=log_path
        )
        service_tier = sv.api.session_settings.service(sv).normalize_requested_service_tier(meta.get("service_tier"))
    except Exception as exc:
        if skip_invalid_sidecars:
            manager.quarantine_sidecar(sock, exc, log=False)
            return
        raise

    try:
        resp = manager.sock_call(sock, {"cmd": "state"}, timeout_s=0.5)
    except Exception as exc:
        if sv.api.probe_failure_safe_to_prune(broker_pid=broker_pid, codex_pid=codex_pid):
            sv.api.unlink_quiet(sock)
            sv.api.unlink_quiet(meta_path)
            return
        if (not sv.api.sock_error_definitely_stale(exc)) and (not skip_invalid_sidecars):
            sv.api.sys.stderr.write(
                f"error: discover: sock state call failed for {sock}: {type(exc).__name__}: {exc}\n"
            )
            sv.api.sys.stderr.flush()
        resp = {"busy": False, "queue_len": 0, "token": None}

    queue_len_raw = resp.get("queue_len") if isinstance(resp, dict) else None
    if (
        not isinstance(resp, dict)
        or not isinstance(resp.get("busy"), bool)
        or type(queue_len_raw) is not int
        or int(queue_len_raw) < 0
    ):
        state_error = ValueError(f"invalid broker state response for socket {sock}")
        if skip_invalid_sidecars:
            return
        raise state_error

    meta_log_off = int(log_path.stat().st_size) if log_path is not None else 0
    queue_len = int(queue_len_raw) if type(queue_len_raw) is int and int(queue_len_raw) >= 0 else 0
    session = sv.api.Session(
        session_id=session_id,
        thread_id=thread_id,
        broker_pid=broker_pid,
        codex_pid=codex_pid,
        agent_backend=agent_backend,
        owned=owned,
        backend=backend,
        transport=transport,
        supports_live_ui=supports_live_ui,
        ui_protocol_version=ui_protocol_version,
        start_ts=float(start_ts),
        cwd=str(cwd),
        log_path=log_path,
        sock_path=sock,
        session_path=session_path,
        busy=sv.api.state_busy_value(resp),
        queue_len=queue_len,
        token=resp.get("token") if isinstance(resp.get("token"), (dict, type(None))) else None,
        meta_thinking=0,
        meta_tools=0,
        meta_system=0,
        meta_log_off=meta_log_off,
        model_provider=model_provider,
        preferred_auth_method=preferred_auth_method,
        model=model,
        reasoning_effort=reasoning_effort,
        service_tier=service_tier,
        tmux_session=tmux_session,
        tmux_window=tmux_window,
        resume_session_id=resume_session_id,
        pi_session_path_discovered=session_path_discovered,
    )
    with manager._lock:
        prev = manager._sessions.get(session_id)
        if not prev:
            manager.reset_log_caches(session, meta_log_off=meta_log_off)
            session.model_provider = model_provider
            session.preferred_auth_method = preferred_auth_method
            session.model = model
            session.reasoning_effort = reasoning_effort
            session.service_tier = service_tier
            manager._sessions[session_id] = session
        else:
            prev.sock_path = session.sock_path
            prev.thread_id = session.thread_id
            prev.backend = session.backend
            prev.broker_pid = session.broker_pid
            prev.codex_pid = session.codex_pid
            prev.agent_backend = session.agent_backend
            prev.owned = session.owned
            prev.transport = session.transport
            prev.supports_live_ui = session.supports_live_ui
            prev.ui_protocol_version = session.ui_protocol_version
            prev.start_ts = session.start_ts
            prev.cwd = session.cwd
            prev.busy = session.busy
            prev.queue_len = session.queue_len
            prev.token = session.token
            manager.apply_session_source(prev, log_path=session.log_path, session_path=session.session_path)
            prev.model_provider = model_provider
            prev.preferred_auth_method = preferred_auth_method
            prev.model = model
            prev.reasoning_effort = reasoning_effort
            prev.service_tier = service_tier
            prev.tmux_session = tmux_session
            prev.tmux_window = tmux_window
            prev.resume_session_id = resume_session_id
            prev.pi_session_path_discovered = session.pi_session_path_discovered or prev.pi_session_path_discovered


def discover_existing(
    manager: Any,
    *,
    force: bool = False,
    skip_invalid_sidecars: bool = False,
) -> None:
    sv = manager_runtime(manager)
    if not force:
        now = time.time()
        with manager._lock:
            last = float(manager._last_discover_ts)
        if (now - last) < sv.api.DISCOVER_MIN_INTERVAL_SECONDS:
            return

    sv.api.SOCK_DIR.mkdir(parents=True, exist_ok=True)
    for sock in sorted(sv.api.SOCK_DIR.glob("*.sock")):
        if skip_invalid_sidecars and manager.sidecar_is_quarantined(sock):
            continue
        _discover_one_socket(
            manager,
            sv,
            sock,
            skip_invalid_sidecars=skip_invalid_sidecars,
        )

    with manager._lock:
        manager._last_discover_ts = time.time()
