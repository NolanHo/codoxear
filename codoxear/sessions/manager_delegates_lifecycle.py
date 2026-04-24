from __future__ import annotations

from typing import Any

from .manager_delegates_shared import _sv


class SessionManagerLifecycleDelegates:
    def page_state_ref_for_session(self, session: Any):
        durable_id = _sv(self).api.clean_optional_text(session.thread_id) or _sv(self).api.clean_optional_text(session.session_id)
        if durable_id is None:
            return None
        backend = _sv(self).api.normalize_agent_backend(
            session.agent_backend,
            default=session.backend or "codex",
        )
        return backend, durable_id

    def _page_state_ref_for_session(self, session: Any):
        return self.page_state_ref_for_session(session)

    def durable_session_id_for_session(self, session: Any) -> str:
        ref = self.page_state_ref_for_session(session)
        if ref is not None:
            return ref[1]
        return str(session.session_id)

    def _durable_session_id_for_session(self, session: Any) -> str:
        return self.durable_session_id_for_session(session)

    def runtime_session_id_for_identifier(self, session_id: str) -> str | None:
        return _sv(self).api.session_catalog.service(self).runtime_session_id_for_identifier(session_id)

    def durable_session_id_for_identifier(self, session_id: str) -> str | None:
        return _sv(self).api.session_catalog.service(self).durable_session_id_for_identifier(session_id)

    def _runtime_session_id_for_identifier(self, session_id: str) -> str | None:
        return self.runtime_session_id_for_identifier(session_id)

    def _durable_session_id_for_identifier(self, session_id: str) -> str | None:
        return self.durable_session_id_for_identifier(session_id)

    def _append_bridge_event(self, durable_session_id: str, event: dict[str, Any]) -> dict[str, Any]:
        key = _sv(self).api.clean_optional_text(durable_session_id)
        if key is None:
            raise ValueError("durable session id required")
        with self._lock:
            offsets = getattr(self, "_bridge_event_offsets", None)
            if not isinstance(offsets, dict):
                self._bridge_event_offsets = {}
                offsets = self._bridge_event_offsets
            rows_by_session = getattr(self, "_bridge_events", None)
            if not isinstance(rows_by_session, dict):
                self._bridge_events = {}
                rows_by_session = self._bridge_events
            next_offset = int(offsets.get(key, 0)) + 1
            offsets[key] = next_offset
            stamped = dict(event)
            stamped["event_id"] = str(stamped.get("event_id") or f"bridge:{key}:{next_offset}")
            stamped["ts"] = float(stamped.get("ts") or _sv(self).api.time.time())
            rows_by_session.setdefault(key, []).append({"offset": next_offset, "event": stamped})
            rows = rows_by_session[key]
            if len(rows) > 64:
                rows_by_session[key] = rows[-64:]
        _sv(self).api.publish_session_live_invalidate(key, reason="bridge_event")
        return stamped

    def _bridge_events_since(self, durable_session_id: str, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        key = _sv(self).api.clean_optional_text(durable_session_id)
        if key is None:
            return [], max(0, int(offset))
        with self._lock:
            rows_by_session = getattr(self, "_bridge_events", None)
            offsets = getattr(self, "_bridge_event_offsets", None)
            rows = list(rows_by_session.get(key, [])) if isinstance(rows_by_session, dict) else []
            latest = int(offsets.get(key, 0)) if isinstance(offsets, dict) else 0
        since = max(0, int(offset))
        events: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if int(row.get("offset", 0) or 0) <= since:
                continue
            event = row.get("event")
            if isinstance(event, dict):
                events.append(dict(event))
        return events, latest

    def _set_bridge_transport_state(
        self,
        runtime_id: str,
        *,
        state: str,
        error: str | None = None,
        checked_ts: float | None = None,
    ) -> None:
        _sv(self).api.session_background.service(self).set_bridge_transport_state(
            runtime_id,
            state=state,
            error=error,
            checked_ts=checked_ts,
        )

    def probe_bridge_transport(
        self,
        session_id: str,
        *,
        force_rpc: bool = False,
    ) -> tuple[str, str | None]:
        return _sv(self).api.session_background.service(self).probe_bridge_transport(
            session_id,
            force_rpc=force_rpc,
        )

    def _probe_bridge_transport(
        self,
        session_id: str,
        *,
        force_rpc: bool = False,
    ) -> tuple[str, str | None]:
        return self.probe_bridge_transport(session_id, force_rpc=force_rpc)

    def enqueue_outbound_request(self, runtime_id: str, text: str):
        return _sv(self).api.session_background.service(self).enqueue_outbound_request(runtime_id, text)

    def _enqueue_outbound_request(self, runtime_id: str, text: str):
        return self.enqueue_outbound_request(runtime_id, text)

    def _fail_outbound_request(self, request: Any, error: str) -> None:
        _sv(self).api.session_background.service(self).fail_outbound_request(request, error)

    def _mark_outbound_request_buffered_for_compaction(self, request: Any) -> None:
        _sv(self).api.session_background.service(self).mark_outbound_request_buffered_for_compaction(request)

    def _maybe_drain_outbound_request(self, runtime_id: str) -> bool:
        return _sv(self).api.session_background.service(self).maybe_drain_outbound_request(runtime_id)

    def _catalog_record_for_ref(self, ref: Any):
        return _sv(self).api.session_lifecycle.service(self).catalog_record_for_ref(ref)

    def _refresh_durable_session_catalog(self, *, force: bool = False) -> None:
        _sv(self).api.session_lifecycle.service(self).refresh_durable_session_catalog(force=force)

    def page_state_ref_for_session_id(self, session_id: str):
        return _sv(self).api.session_catalog.service(self).page_state_ref_for_session_id(session_id)

    def _page_state_ref_for_session_id(self, session_id: str):
        return self.page_state_ref_for_session_id(session_id)

    def _persist_durable_session_record(self, row: Any) -> None:
        db = getattr(self, "_page_state_db", None)
        if isinstance(db, _sv(self).api.PageStateDB):
            db.upsert_session(row)

    def _delete_durable_session_record(self, ref: Any | None) -> None:
        db = getattr(self, "_page_state_db", None)
        if ref is not None and isinstance(db, _sv(self).api.PageStateDB):
            db.delete_session(ref)

    def _wait_for_live_session(
        self,
        durable_session_id: str,
        *,
        timeout_s: float = 8.0,
    ):
        return _sv(self).api.session_lifecycle.service(self).wait_for_live_session(
            durable_session_id,
            timeout_s=timeout_s,
        )

    def _copy_session_ui_identity(
        self,
        *,
        source_session_id: str,
        target_session_id: str,
    ) -> str | None:
        return _sv(self).api.session_lifecycle.service(self).copy_session_ui_identity(
            source_session_id=source_session_id,
            target_session_id=target_session_id,
        )

    def _capture_runtime_bound_restart_state(self, runtime_id: str, ref: Any) -> dict[str, Any]:
        return _sv(self).api.session_lifecycle.service(self).capture_runtime_bound_restart_state(runtime_id, ref)

    def _stage_runtime_bound_restart_state(self, runtime_id: str, ref: Any, state: dict[str, Any]) -> None:
        _sv(self).api.session_lifecycle.service(self).stage_runtime_bound_restart_state(runtime_id, ref, state)

    def _restore_runtime_bound_restart_state(self, runtime_id: str, ref: Any, state: dict[str, Any]) -> None:
        _sv(self).api.session_lifecycle.service(self).restore_runtime_bound_restart_state(runtime_id, ref, state)

    def _finalize_pending_pi_restart_state(
        self,
        *,
        durable_session_id: str,
        ref: Any,
        state: dict[str, Any],
        timeout_s: float = 8.0,
    ) -> None:
        try:
            session = self._wait_for_live_session(durable_session_id, timeout_s=timeout_s)
        except Exception:
            return
        self._restore_runtime_bound_restart_state(session.session_id, ref, state)

    def restart_session(self, session_id: str) -> dict[str, Any]:
        return _sv(self).api.session_control.service(self).restart_session(session_id)

    def handoff_session(self, session_id: str) -> dict[str, Any]:
        return _sv(self).api.session_control.service(self).handoff_session(session_id)

    def _finalize_pending_pi_spawn(
        self,
        *,
        spawn_nonce: str,
        durable_session_id: str,
        cwd: str,
        session_path: Any,
        proc: Any = None,
        delete_on_failure: bool = True,
        restore_record_on_failure: Any | None = None,
    ) -> None:
        _sv(self).api.session_lifecycle.service(self).finalize_pending_pi_spawn(
            spawn_nonce=spawn_nonce,
            durable_session_id=durable_session_id,
            cwd=cwd,
            session_path=session_path,
            proc=proc,
            delete_on_failure=delete_on_failure,
            restore_record_on_failure=restore_record_on_failure,
        )

