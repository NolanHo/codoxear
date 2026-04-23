from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..agent_backend import normalize_agent_backend
from ..page_state_sqlite import PageStateDB, SessionRef
from . import catalog_discovery as _catalog_discovery
from . import catalog_listing as _catalog_listing
from . import catalog_state as _catalog_state


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
    _catalog_discovery.discover_existing(
        manager,
        force=force,
        skip_invalid_sidecars=skip_invalid_sidecars,
    )


def refresh_session_state(
    manager: Any, session_id: str, sock_path: Path, timeout_s: float = 0.4
) -> tuple[bool, BaseException | None]:
    return _catalog_state.refresh_session_state(
        manager,
        session_id,
        sock_path,
        timeout_s=timeout_s,
    )


def prune_dead_sessions(manager: Any) -> None:
    _catalog_state.prune_dead_sessions(manager)
