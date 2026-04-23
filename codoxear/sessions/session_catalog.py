from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..agent_backend import normalize_agent_backend
from ..page_state_sqlite import PageStateDB, SessionRef
from . import catalog_listing as _catalog_listing


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


@dataclass(slots=True)
class SessionCatalogService:
    manager: Any

    def listed_session_row(self, session_id: str) -> dict[str, Any] | None:
        return listed_session_row(self.manager, session_id)

    def runtime_session_id_for_identifier(self, session_id: str) -> str | None:
        return runtime_session_id_for_identifier(self.manager, session_id)

    def durable_session_id_for_identifier(self, session_id: str) -> str | None:
        return durable_session_id_for_identifier(self.manager, session_id)

    def page_state_ref_for_session_id(self, session_id: str) -> SessionRef | None:
        return page_state_ref_for_session_id(self.manager, session_id)

    def discover_existing(
        self, *, force: bool = False, skip_invalid_sidecars: bool = False
    ) -> None:
        discover_existing(
            self.manager,
            force=force,
            skip_invalid_sidecars=skip_invalid_sidecars,
        )

    def refresh_session_state(
        self, session_id: str, sock_path: Path, timeout_s: float = 0.4
    ) -> tuple[bool, BaseException | None]:
        return refresh_session_state(
            self.manager,
            session_id,
            sock_path,
            timeout_s=timeout_s,
        )

    def prune_dead_sessions(self) -> None:
        prune_dead_sessions(self.manager)

    def list_sessions(self) -> list[dict[str, Any]]:
        return list_sessions(self.manager)

    def get_session(self, session_id: str) -> Any | None:
        return get_session(self.manager, session_id)

    def refresh_session_meta(self, session_id: str, *, strict: bool = True) -> None:
        refresh_session_meta(self.manager, session_id, strict=strict)


def service(manager: Any) -> SessionCatalogService:
    return SessionCatalogService(manager)


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


def refresh_session_meta(manager: Any, session_id: str, *, strict: bool = True) -> None:
    sv = manager._runtime
    runtime_id = runtime_session_id_for_identifier(manager, session_id)
    if runtime_id is None:
        return
    with manager._lock:
        session = manager._sessions.get(runtime_id)
        if not session:
            return
        sock = session.sock_path
    try:
        meta_path = sock.with_suffix(".json")
        if not meta_path.exists():
            raise RuntimeError(f"missing metadata sidecar for socket {sock}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            raise ValueError(f"invalid metadata json for socket {sock}")

        thread_id = _clean_optional_text(meta.get("session_id")) or session.thread_id
        backend = normalize_agent_backend(
            meta.get("backend"),
            default=normalize_agent_backend(meta.get("agent_backend"), default=session.backend),
        )
        agent_backend = normalize_agent_backend(meta.get("agent_backend"), default=backend)
        owned = (meta.get("owner") == "web") if isinstance(meta.get("owner"), str) else session.owned
        transport, tmux_session, tmux_window = manager._session_transport(meta=meta)
        supports_live_ui = meta.get("supports_live_ui") if isinstance(meta.get("supports_live_ui"), bool) else None
        ui_protocol_version_raw = meta.get("ui_protocol_version")
        ui_protocol_version = ui_protocol_version_raw if type(ui_protocol_version_raw) is int else None
        log_path = sv.api.metadata_log_path(meta=meta, backend=backend, sock=sock)
        session_path_discovered = False
        if backend == "pi":
            preferred_session_path: Path | None = session.session_path
            if strict or ("session_path" in meta):
                preferred_session_path = sv.api.metadata_session_path(meta=meta, backend=backend, sock=sock)
            claimed: set[Path] | None = (
                manager._claimed_pi_session_paths(exclude_sid=session_id)
                if preferred_session_path is None
                else None
            )
            session_path, session_path_source = sv.api.resolve_pi_session_path(
                thread_id=thread_id,
                cwd=str(meta.get("cwd") or session.cwd),
                start_ts=float(meta.get("start_ts") or session.start_ts),
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
            session_path = sv.api.metadata_session_path(meta=meta, backend=backend, sock=sock)
        if log_path is not None and log_path.exists():
            thread_id, log_path = sv.api.coerce_main_thread_log(thread_id=thread_id, log_path=log_path)

        cwd_raw = meta.get("cwd")
        if not isinstance(cwd_raw, str) or (not cwd_raw.strip()):
            raise ValueError(f"invalid cwd in metadata for socket {sock}")
        cwd = cwd_raw

        start_ts_raw = meta.get("start_ts")
        start_ts = float(start_ts_raw) if isinstance(start_ts_raw, (int, float)) else session.start_ts
        resume_session_id = _clean_optional_text(meta.get("resume_session_id"))
        model_provider, preferred_auth_method, model, reasoning_effort = manager._session_run_settings(
            backend=backend,
            meta=meta,
            log_path=log_path,
        )
        service_tier = sv.api.normalize_requested_service_tier(meta.get("service_tier"))
    except Exception as exc:
        if strict:
            raise
        manager._quarantine_sidecar(sock, exc, log=False)
        return
    manager._clear_sidecar_quarantine(sock)

    pi_session_switched = False
    old_session_path: Path | None = None
    with manager._lock:
        current = manager._sessions.get(session_id)
        if (
            current
            and backend == "pi"
            and current.thread_id
            and thread_id
            and current.thread_id != thread_id
            and current.session_path is not None
        ):
            pi_session_switched = True
            old_session_path = current.session_path

    if pi_session_switched and old_session_path is not None:
        claimed = manager._claimed_pi_session_paths(exclude_sid=session_id)
        claimed.add(old_session_path)
        new_sp, new_sp_source = sv.api.resolve_pi_session_path(
            thread_id=thread_id,
            cwd=cwd,
            start_ts=start_ts,
            preferred=None,
            exclude=claimed,
        )
        if new_sp is not None and new_sp != old_session_path:
            session_path = new_sp
            if new_sp_source in {"exact", "discovered"}:
                session_path_discovered = True
            sv.api.patch_metadata_session_path(sock, new_sp, force=True)

    with manager._lock:
        current = manager._sessions.get(session_id)
        if not current:
            return
        if pi_session_switched:
            current.session_path = None
            current.pi_attention_scan_activity_ts = None
            manager._reset_log_caches(current, meta_log_off=0)
        current.thread_id = str(thread_id)
        current.agent_backend = agent_backend
        current.backend = backend
        current.cwd = str(cwd)
        current.owned = bool(owned)
        current.transport = transport
        current.supports_live_ui = supports_live_ui
        current.ui_protocol_version = ui_protocol_version
        manager._apply_session_source(current, log_path=log_path, session_path=session_path)
        current.model_provider = model_provider
        current.preferred_auth_method = preferred_auth_method
        current.model = model
        current.reasoning_effort = reasoning_effort
        current.service_tier = service_tier
        current.tmux_session = tmux_session
        current.tmux_window = tmux_window
        current.resume_session_id = resume_session_id
        current.pi_session_path_discovered = bool(current.pi_session_path_discovered or session_path_discovered)
    if manager._queue_len(session_id) > 0:
        manager._maybe_drain_session_queue(session_id)


def list_sessions(manager: Any) -> list[dict[str, Any]]:
    return _catalog_listing.list_sessions(manager)


def discover_existing(
    manager: Any, *, force: bool = False, skip_invalid_sidecars: bool = False
) -> None:
    sv = manager._runtime
    if not force:
        now = time.time()
        with manager._lock:
            last = float(manager._last_discover_ts)
        if (now - last) < sv.api.DISCOVER_MIN_INTERVAL_SECONDS:
            return
    sv.api.SOCK_DIR.mkdir(parents=True, exist_ok=True)
    for sock in sorted(sv.api.SOCK_DIR.glob("*.sock")):
        if skip_invalid_sidecars and manager._sidecar_is_quarantined(sock):
            continue
        session_id = sock.stem
        try:
            meta_path = sock.with_suffix(".json")
            if not meta_path.exists():
                continue
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
            transport, tmux_session, tmux_window = manager._session_transport(meta=meta)
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
                    ignored_paths = manager._claimed_pi_session_paths(exclude_sid=session_id)
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
                    continue
                if supports_live_ui is not True:
                    continue
                if not isinstance(ui_protocol_version, int) or ui_protocol_version < 1:
                    continue
                if (not owned) and (not sv.api.supports_web_control(meta)):
                    continue

            log_path = sv.api.metadata_log_path(meta=meta, backend=backend, sock=sock)
            if inferred_pi_session_path is not None:
                session_path = inferred_pi_session_path
            else:
                preferred_session_path: Path | None = None
                if backend == "pi":
                    try:
                        preferred_session_path = sv.api.metadata_session_path(meta=meta, backend=backend, sock=sock)
                    except ValueError as exc:
                        if "missing session_path" not in str(exc):
                            raise
                    claimed: set[Path] | None = (
                        manager._claimed_pi_session_paths(exclude_sid=session_id)
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
                    session_path = sv.api.metadata_session_path(meta=meta, backend=backend, sock=sock)
            if log_path is not None and log_path.exists():
                thread_id, log_path = sv.api.coerce_main_thread_log(thread_id=thread_id, log_path=log_path)
            else:
                log_path = None
        except Exception as exc:
            if skip_invalid_sidecars:
                manager._quarantine_sidecar(sock, exc, log=False)
                continue
            raise
        manager._clear_sidecar_quarantine(sock)

        if (log_path is None) and (not sv.api.pid_alive(codex_pid)) and (not sv.api.pid_alive(broker_pid)):
            manager._unhide_session(session_id)
            sv.api.unlink_quiet(sock)
            sv.api.unlink_quiet(meta_path)
            continue
        resume_session_id = _clean_optional_text(meta.get("resume_session_id"))
        if manager._session_is_hidden(session_id, thread_id, resume_session_id, agent_backend):
            if (not sv.api.pid_alive(codex_pid)) and (not sv.api.pid_alive(broker_pid)):
                manager._unhide_session(session_id)
                sv.api.unlink_quiet(sock)
                sv.api.unlink_quiet(meta_path)
            continue

        try:
            model_provider, preferred_auth_method, model, reasoning_effort = manager._session_run_settings(
                backend=backend, meta=meta, log_path=log_path
            )
            service_tier = sv.api.normalize_requested_service_tier(meta.get("service_tier"))
        except Exception as exc:
            if skip_invalid_sidecars:
                manager._quarantine_sidecar(sock, exc, log=False)
                continue
            raise
        try:
            resp = manager._sock_call(sock, {"cmd": "state"}, timeout_s=0.5)
        except Exception as exc:
            if sv.api.probe_failure_safe_to_prune(broker_pid=broker_pid, codex_pid=codex_pid):
                sv.api.unlink_quiet(sock)
                sv.api.unlink_quiet(meta_path)
                continue
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
                continue
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
                manager._reset_log_caches(session, meta_log_off=meta_log_off)
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
                manager._apply_session_source(prev, log_path=session.log_path, session_path=session.session_path)
                prev.model_provider = model_provider
                prev.preferred_auth_method = preferred_auth_method
                prev.model = model
                prev.reasoning_effort = reasoning_effort
                prev.service_tier = service_tier
                prev.tmux_session = tmux_session
                prev.tmux_window = tmux_window
                prev.resume_session_id = resume_session_id
                prev.pi_session_path_discovered = session.pi_session_path_discovered or prev.pi_session_path_discovered
    with manager._lock:
        manager._last_discover_ts = time.time()


def refresh_session_state(
    manager: Any, session_id: str, sock_path: Path, timeout_s: float = 0.4
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
            broker_pid=session.broker_pid, codex_pid=session.codex_pid
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
