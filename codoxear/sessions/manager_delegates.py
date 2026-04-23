from __future__ import annotations

from typing import Any

from .runtime_access import manager_runtime


def _sv(manager: Any):
    return manager_runtime(manager)


class SessionManagerDelegates:
    def _page_state_ref_for_session(self, session: Any):
        durable_id = _sv(self)._clean_optional_text(session.thread_id) or _sv(self)._clean_optional_text(session.session_id)
        if durable_id is None:
            return None
        backend = _sv(self).normalize_agent_backend(
            session.agent_backend,
            default=session.backend or "codex",
        )
        return backend, durable_id

    def _durable_session_id_for_session(self, session: Any) -> str:
        ref = self._page_state_ref_for_session(session)
        if ref is not None:
            return ref[1]
        return str(session.session_id)

    def _runtime_session_id_for_identifier(self, session_id: str) -> str | None:
        return _sv(self)._session_catalog.service(self).runtime_session_id_for_identifier(session_id)

    def _durable_session_id_for_identifier(self, session_id: str) -> str | None:
        return _sv(self)._session_catalog.service(self).durable_session_id_for_identifier(session_id)

    def _append_bridge_event(self, durable_session_id: str, event: dict[str, Any]) -> dict[str, Any]:
        key = _sv(self)._clean_optional_text(durable_session_id)
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
            stamped["ts"] = float(stamped.get("ts") or _sv(self).time.time())
            rows_by_session.setdefault(key, []).append({"offset": next_offset, "event": stamped})
            rows = rows_by_session[key]
            if len(rows) > 64:
                rows_by_session[key] = rows[-64:]
        _sv(self)._publish_session_live_invalidate(key, reason="bridge_event")
        return stamped

    def _bridge_events_since(self, durable_session_id: str, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        key = _sv(self)._clean_optional_text(durable_session_id)
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
        _sv(self)._session_background.service(self).set_bridge_transport_state(
            runtime_id,
            state=state,
            error=error,
            checked_ts=checked_ts,
        )

    def _probe_bridge_transport(
        self,
        session_id: str,
        *,
        force_rpc: bool = False,
    ) -> tuple[str, str | None]:
        return _sv(self)._session_background.service(self).probe_bridge_transport(
            session_id,
            force_rpc=force_rpc,
        )

    def _enqueue_outbound_request(self, runtime_id: str, text: str):
        return _sv(self)._session_background.service(self).enqueue_outbound_request(runtime_id, text)

    def _fail_outbound_request(self, request: Any, error: str) -> None:
        _sv(self)._session_background.service(self).fail_outbound_request(request, error)

    def _mark_outbound_request_buffered_for_compaction(self, request: Any) -> None:
        _sv(self)._session_background.service(self).mark_outbound_request_buffered_for_compaction(request)

    def _maybe_drain_outbound_request(self, runtime_id: str) -> bool:
        return _sv(self)._session_background.service(self).maybe_drain_outbound_request(runtime_id)

    def _catalog_record_for_ref(self, ref: Any):
        return _sv(self)._session_lifecycle.service(self).catalog_record_for_ref(ref)

    def _refresh_durable_session_catalog(self, *, force: bool = False) -> None:
        _sv(self)._session_lifecycle.service(self).refresh_durable_session_catalog(force=force)

    def _page_state_ref_for_session_id(self, session_id: str):
        return _sv(self)._session_catalog.service(self).page_state_ref_for_session_id(session_id)

    def _persist_durable_session_record(self, row: Any) -> None:
        db = getattr(self, "_page_state_db", None)
        if isinstance(db, _sv(self).PageStateDB):
            db.upsert_session(row)

    def _delete_durable_session_record(self, ref: Any | None) -> None:
        db = getattr(self, "_page_state_db", None)
        if ref is not None and isinstance(db, _sv(self).PageStateDB):
            db.delete_session(ref)

    def _wait_for_live_session(
        self,
        durable_session_id: str,
        *,
        timeout_s: float = 8.0,
    ):
        return _sv(self)._session_lifecycle.service(self).wait_for_live_session(
            durable_session_id,
            timeout_s=timeout_s,
        )

    def _copy_session_ui_identity(
        self,
        *,
        source_session_id: str,
        target_session_id: str,
    ) -> str | None:
        return _sv(self)._session_lifecycle.service(self).copy_session_ui_identity(
            source_session_id=source_session_id,
            target_session_id=target_session_id,
        )

    def _capture_runtime_bound_restart_state(self, runtime_id: str, ref: Any) -> dict[str, Any]:
        return _sv(self)._session_lifecycle.service(self).capture_runtime_bound_restart_state(runtime_id, ref)

    def _stage_runtime_bound_restart_state(self, runtime_id: str, ref: Any, state: dict[str, Any]) -> None:
        _sv(self)._session_lifecycle.service(self).stage_runtime_bound_restart_state(runtime_id, ref, state)

    def _restore_runtime_bound_restart_state(self, runtime_id: str, ref: Any, state: dict[str, Any]) -> None:
        _sv(self)._session_lifecycle.service(self).restore_runtime_bound_restart_state(runtime_id, ref, state)

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
        return _sv(self)._session_control.service(self).restart_session(session_id)

    def handoff_session(self, session_id: str) -> dict[str, Any]:
        return _sv(self)._session_control.service(self).handoff_session(session_id)

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
        _sv(self)._session_lifecycle.service(self).finalize_pending_pi_spawn(
            spawn_nonce=spawn_nonce,
            durable_session_id=durable_session_id,
            cwd=cwd,
            session_path=session_path,
            proc=proc,
            delete_on_failure=delete_on_failure,
            restore_record_on_failure=restore_record_on_failure,
        )

    def _persist_session_ui_state(self) -> None:
        self._sidebar_state_facade().persist_session_ui_state()

    def _persist_files(self) -> None:
        db = getattr(self, "_page_state_db", None)
        if db is None:
            return
        with self._lock:
            files_src = dict(self._files)
        rows: dict[Any, list[str]] = {}
        for key, value in files_src.items():
            ref = key if isinstance(key, tuple) and len(key) == 2 else self._page_state_ref_for_session_id(str(key))
            if ref is None or not isinstance(value, list):
                continue
            rows[ref] = [row for row in value if isinstance(row, str) and row.strip()]
        db.save_files(rows)

    def _persist_queues(self) -> None:
        db = getattr(self, "_page_state_db", None)
        if db is None:
            return
        with self._lock:
            queues_src = dict(self._queues)
        rows: dict[Any, list[str]] = {}
        for key, value in queues_src.items():
            ref = key if isinstance(key, tuple) and len(key) == 2 else self._page_state_ref_for_session_id(str(key))
            if ref is None or not isinstance(value, list):
                continue
            rows[ref] = [row for row in value if isinstance(row, str) and row.strip()]
        db.save_queues(rows)

    def _persist_recent_cwds(self) -> None:
        db = getattr(self, "_page_state_db", None)
        if db is None:
            return
        with self._lock:
            recent_cwds = dict(self._recent_cwds)
        db.save_recent_cwds(recent_cwds)

    def _persist_cwd_groups(self) -> None:
        db = getattr(self, "_page_state_db", None)
        if db is None:
            return
        with self._lock:
            cwd_groups = dict(self._cwd_groups)
        db.save_cwd_groups(cwd_groups)

    def _reset_log_caches(self, s: Any, *, meta_log_off: int) -> None:
        _sv(self)._session_lifecycle.service(self).reset_log_caches(s, meta_log_off=meta_log_off)

    def _session_source_changed(self, s: Any, *, log_path: Any, session_path: Any) -> bool:
        return _sv(self)._session_lifecycle.service(self).session_source_changed(
            s,
            log_path=log_path,
            session_path=session_path,
        )

    def _claimed_pi_session_paths(self, *, exclude_sid: str = "") -> set[Any]:
        return _sv(self)._session_lifecycle.service(self).claimed_pi_session_paths(exclude_sid=exclude_sid)

    def _apply_session_source(self, s: Any, *, log_path: Any, session_path: Any) -> None:
        _sv(self)._session_lifecycle.service(self).apply_session_source(
            s,
            log_path=log_path,
            session_path=session_path,
        )

    def _session_run_settings(
        self,
        *,
        meta: dict[str, Any],
        log_path: Any,
        backend: str | None = None,
        agent_backend: str | None = None,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        return _sv(self)._session_lifecycle.service(self).session_run_settings(
            meta=meta,
            log_path=log_path,
            backend=backend,
            agent_backend=agent_backend,
        )

    def _session_transport(self, *, meta: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        transport = _sv(self)._clean_optional_text(meta.get("transport"))
        tmux_session = _sv(self)._clean_optional_text(meta.get("tmux_session"))
        tmux_window = _sv(self)._clean_optional_text(meta.get("tmux_window"))
        if transport is None and (tmux_session is not None or tmux_window is not None):
            transport = "tmux"
        return transport, tmux_session, tmux_window

    def _discover_existing_if_stale(self, *, force: bool = False) -> None:
        now = _sv(self).time.time()
        with self._lock:
            last = float(getattr(self, "_last_discover_ts", 0.0))
        if (not force) and ((now - last) < _sv(self).DISCOVER_MIN_INTERVAL_SECONDS):
            return
        try:
            self._discover_existing(force=force, skip_invalid_sidecars=True)
        except TypeError:
            try:
                self._discover_existing(force=force)
            except TypeError:
                self._discover_existing()

    def _sidecar_quarantine_signature(self, sock: Any) -> tuple[bool, int, int]:
        meta_path = sock.with_suffix(".json")
        try:
            st = meta_path.stat()
        except FileNotFoundError:
            return (False, 0, 0)
        return (True, int(st.st_mtime_ns), int(st.st_size))

    def _sidecar_is_quarantined(self, sock: Any) -> bool:
        bad_sidecars = getattr(self, "_bad_sidecars", None)
        if not isinstance(bad_sidecars, dict):
            self._bad_sidecars = {}
            bad_sidecars = self._bad_sidecars
        key = str(sock)
        prev_sig = bad_sidecars.get(key)
        if prev_sig is None:
            return False
        cur_sig = self._sidecar_quarantine_signature(sock)
        if cur_sig == prev_sig:
            return True
        bad_sidecars.pop(key, None)
        return False

    def _quarantine_sidecar(
        self,
        sock: Any,
        exc: BaseException,
        *,
        reason: str = "invalid sidecar",
        log: bool = True,
    ) -> None:
        bad_sidecars = getattr(self, "_bad_sidecars", None)
        if not isinstance(bad_sidecars, dict):
            self._bad_sidecars = {}
            bad_sidecars = self._bad_sidecars
        bad_sidecars[str(sock)] = self._sidecar_quarantine_signature(sock)
        if log:
            _sv(self).sys.stderr.write(
                f"error: discover: quarantining {reason} for {sock}: {type(exc).__name__}: {exc}\\n"
            )
            _sv(self).sys.stderr.flush()

    def _clear_sidecar_quarantine(self, sock: Any) -> None:
        bad_sidecars = getattr(self, "_bad_sidecars", None)
        if isinstance(bad_sidecars, dict):
            bad_sidecars.pop(str(sock), None)

    def _load_harness(self) -> None:
        _sv(self)._page_state.service(self).load_harness()

    def _save_harness(self) -> None:
        _sv(self)._page_state.service(self).save_harness()

    def _load_aliases(self) -> None:
        self._sidebar_state_facade().load_aliases()

    def _save_aliases(self) -> None:
        self._persist_session_ui_state()

    def _load_sidebar_meta(self) -> None:
        self._sidebar_state_facade().load_sidebar_meta()

    def _save_sidebar_meta(self) -> None:
        self._persist_session_ui_state()

    def _load_hidden_sessions(self) -> None:
        self._sidebar_state_facade().load_hidden_sessions()

    def _save_hidden_sessions(self) -> None:
        self._persist_session_ui_state()

    def _hidden_session_keys(
        self,
        session_id: str | None,
        thread_id: str | None,
        resume_session_id: str | None,
        backend: str | None,
    ) -> set[str]:
        return self._sidebar_state_facade().hidden_session_keys(
            session_id,
            thread_id,
            resume_session_id,
            backend,
        )

    def _session_is_hidden(
        self,
        session_id: str | None,
        thread_id: str | None,
        resume_session_id: str | None,
        backend: str | None,
    ) -> bool:
        return self._sidebar_state_facade().session_is_hidden(
            session_id,
            thread_id,
            resume_session_id,
            backend,
        )

    def _hide_session(self, session_id: str) -> None:
        self._sidebar_state_facade().hide_session(session_id)

    def _hide_session_identity_values(
        self,
        session_id: str | None,
        thread_id: str | None,
        resume_session_id: str | None,
        backend: str | None,
    ) -> None:
        self._sidebar_state_facade().hide_session_identity_values(
            session_id,
            thread_id,
            resume_session_id,
            backend,
        )

    def _hide_session_identity(self, s: Any) -> None:
        self._sidebar_state_facade().hide_session_identity(s)

    def _unhide_session(self, session_id: str) -> None:
        self._sidebar_state_facade().unhide_session(session_id)

    def set_created_session_name(
        self,
        *,
        session_id: Any,
        runtime_id: Any = None,
        backend: Any = None,
        name: Any,
    ) -> str:
        return self._sidebar_state_facade().set_created_session_name(
            session_id=session_id,
            runtime_id=runtime_id,
            backend=backend,
            name=name,
        )

    def alias_set(self, session_id: str, name: str) -> str:
        alias = self._sidebar_state_facade().alias_set(session_id, name)
        _sv(self)._publish_sessions_invalidate(reason="alias_changed")
        return alias

    def alias_get(self, session_id: str) -> str:
        return self._sidebar_state_facade().alias_get(session_id)

    def alias_clear(self, session_id: str) -> None:
        self._sidebar_state_facade().alias_clear(session_id)
        _sv(self)._publish_sessions_invalidate(reason="alias_cleared")

    def sidebar_meta_get(self, session_id: str) -> dict[str, Any]:
        return self._sidebar_state_facade().sidebar_meta_get(session_id)

    def sidebar_meta_set(
        self,
        session_id: str,
        *,
        priority_offset: Any,
        snooze_until: Any,
        dependency_session_id: Any,
    ) -> dict[str, Any]:
        payload = self._sidebar_state_facade().sidebar_meta_set(
            session_id,
            priority_offset=priority_offset,
            snooze_until=snooze_until,
            dependency_session_id=dependency_session_id,
        )
        _sv(self)._publish_sessions_invalidate(reason="sidebar_meta_changed")
        return payload

    def focus_set(self, session_id: str, focused: Any) -> bool:
        value = self._sidebar_state_facade().focus_set(session_id, focused)
        _sv(self)._publish_sessions_invalidate(reason="focus_changed")
        return value

    def edit_session(
        self,
        session_id: str,
        *,
        name: str,
        priority_offset: Any,
        snooze_until: Any,
        dependency_session_id: Any,
    ) -> tuple[str, dict[str, Any]]:
        payload = self._sidebar_state_facade().edit_session(
            session_id,
            name=name,
            priority_offset=priority_offset,
            snooze_until=snooze_until,
            dependency_session_id=dependency_session_id,
        )
        _sv(self)._publish_sessions_invalidate(reason="session_edited")
        return payload

    def _clear_deleted_session_state(self, session_id: str) -> None:
        _sv(self)._page_state.service(self).clear_deleted_session_state(session_id)

    def _load_files(self) -> None:
        _sv(self)._page_state.service(self).load_files()

    def _save_files(self) -> None:
        _sv(self)._page_state.service(self).save_files()

    def _load_queues(self) -> None:
        _sv(self)._page_state.service(self).load_queues()

    def _save_queues(self) -> None:
        _sv(self)._page_state.service(self).save_queues()

    def _load_recent_cwds(self) -> None:
        _sv(self)._page_state.service(self).load_recent_cwds()

    def _save_recent_cwds(self) -> None:
        _sv(self)._page_state.service(self).save_recent_cwds()

    def _load_cwd_groups(self) -> None:
        _sv(self)._page_state.service(self).load_cwd_groups()

    def _save_cwd_groups(self) -> None:
        _sv(self)._page_state.service(self).save_cwd_groups()

    def cwd_groups_get(self) -> dict[str, dict[str, Any]]:
        return _sv(self)._page_state.service(self).cwd_groups_get()

    def _prune_stale_workspace_dirs(self) -> None:
        _sv(self)._page_state.service(self).prune_stale_workspace_dirs()

    def _known_cwd_group_keys(self) -> set[str]:
        return _sv(self)._page_state.service(self).known_cwd_group_keys()

    def cwd_group_set(
        self,
        cwd: str,
        label: str | None = None,
        collapsed: bool | None = None,
    ) -> tuple[str, dict[str, Any]]:
        return _sv(self)._page_state.service(self).cwd_group_set(
            cwd,
            label=label,
            collapsed=collapsed,
        )

    def _remember_recent_cwd(self, cwd: Any, *, ts: Any = None) -> bool:
        return _sv(self)._page_state.service(self).remember_recent_cwd(cwd, ts=ts)

    def _backfill_recent_cwds_from_logs(self) -> None:
        _sv(self)._page_state.service(self).backfill_recent_cwds_from_logs()

    def recent_cwds(self, *, limit: int | None = None) -> list[str]:
        sv = _sv(self)
        return sv._page_state.service(self).recent_cwds(
            limit=sv.RECENT_CWD_MAX if limit is None else limit
        )

    def _queue_len(self, session_id: str) -> int:
        return _sv(self)._page_state.service(self).queue_len(session_id)

    def _queue_list_local(self, session_id: str) -> list[str]:
        return _sv(self)._page_state.service(self).queue_list_local(session_id)

    def _queue_enqueue_local(self, session_id: str, text: str) -> dict[str, Any]:
        return _sv(self)._page_state.service(self).queue_enqueue_local(session_id, text)

    def _queue_delete_local(self, session_id: str, index: int) -> dict[str, Any]:
        return _sv(self)._page_state.service(self).queue_delete_local(session_id, index)

    def _queue_update_local(
        self,
        session_id: str,
        index: int,
        text: str,
    ) -> dict[str, Any]:
        return _sv(self)._page_state.service(self).queue_update_local(
            session_id,
            index,
            text,
        )

    def _files_key_for_session(self, session_id: str) -> tuple[str, Any, Any]:
        return _sv(self)._page_state.service(self).files_key_for_session(session_id)

    def files_get(self, session_id: str) -> list[str]:
        return _sv(self)._page_state.service(self).files_get(session_id)

    def files_add(self, session_id: str, path: str) -> list[str]:
        return _sv(self)._page_state.service(self).files_add(session_id, path)

    def files_clear(self, session_id: str) -> None:
        _sv(self)._page_state.service(self).files_clear(session_id)

    def harness_get(self, session_id: str) -> dict[str, Any]:
        return _sv(self)._page_state.service(self).harness_get(session_id)

    def harness_set(
        self,
        session_id: str,
        *,
        enabled: bool | None = None,
        request: str | None = None,
        cooldown_minutes: int | None = None,
        remaining_injections: int | None = None,
    ) -> dict[str, Any]:
        return _sv(self)._page_state.service(self).harness_set(
            session_id,
            enabled=enabled,
            request=request,
            cooldown_minutes=cooldown_minutes,
            remaining_injections=remaining_injections,
        )

    def _session_display_name(self, session_id: str) -> str:
        return _sv(self)._session_background.service(self).session_display_name(session_id)

    def _observe_rollout_delta(
        self,
        session_id: str,
        *,
        objs: list[dict[str, Any]],
        new_off: int,
    ) -> None:
        _sv(self)._session_background.service(self).observe_rollout_delta(
            session_id,
            objs=objs,
            new_off=new_off,
        )

    def _voice_push_scan_loop(self) -> None:
        _sv(self)._session_background.service(self).voice_push_scan_loop()

    def _voice_push_scan_sweep(self) -> None:
        _sv(self)._session_background.service(self).voice_push_scan_sweep()

    def _harness_loop(self) -> None:
        _sv(self)._session_background.service(self).harness_loop()

    def _harness_sweep(self) -> None:
        _sv(self)._session_background.service(self).harness_sweep()

    def _queue_loop(self) -> None:
        _sv(self)._session_background.service(self).queue_loop()

    def _maybe_drain_session_queue(
        self,
        session_id: str,
        *,
        now_ts: float | None = None,
    ) -> bool:
        return _sv(self)._session_background.service(self).maybe_drain_session_queue(
            session_id,
            now_ts=now_ts,
        )

    def _queue_sweep(self) -> None:
        _sv(self)._session_background.service(self).queue_sweep()

    def _discover_existing(
        self,
        *,
        force: bool = False,
        skip_invalid_sidecars: bool = False,
    ) -> None:
        _sv(self)._session_catalog.service(self).discover_existing(
            force=force,
            skip_invalid_sidecars=skip_invalid_sidecars,
        )

    def _refresh_session_state(
        self,
        session_id: str,
        sock_path: Any,
        timeout_s: float = 0.4,
    ) -> tuple[bool, BaseException | None]:
        return _sv(self)._session_catalog.service(self).refresh_session_state(
            session_id,
            sock_path,
            timeout_s=timeout_s,
        )

    def _prune_dead_sessions(self) -> None:
        _sv(self)._session_catalog.service(self).prune_dead_sessions()

    def _update_meta_counters(self) -> None:
        _sv(self)._session_background.service(self).update_meta_counters()

    def list_sessions(self) -> list[dict[str, Any]]:
        return _sv(self)._session_catalog.service(self).list_sessions()

    def get_session(self, session_id: str):
        return _sv(self)._session_catalog.service(self).get_session(session_id)

    def refresh_session_meta(self, session_id: str, *, strict: bool = True) -> None:
        _sv(self)._session_catalog.service(self).refresh_session_meta(
            session_id,
            strict=strict,
        )

    def _set_chat_index_snapshot(
        self,
        *,
        session_id: str,
        events: list[dict[str, Any]],
        token_update: dict[str, Any] | None,
        scan_bytes: int,
        scan_complete: bool,
        log_off: int,
    ) -> None:
        _sv(self)._message_history.service(self).set_chat_index_snapshot(
            session_id=session_id,
            events=events,
            token_update=token_update,
            scan_bytes=scan_bytes,
            scan_complete=scan_complete,
            log_off=log_off,
        )

    def _append_chat_events(
        self,
        session_id: str,
        new_events: list[dict[str, Any]],
        *,
        new_off: int,
        latest_token: dict[str, Any] | None,
    ) -> None:
        _sv(self)._message_history.service(self).append_chat_events(
            session_id,
            new_events,
            new_off=new_off,
            latest_token=latest_token,
        )

    def _attach_notification_texts(
        self,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return _sv(self)._message_history.service(self).attach_notification_texts(events)

    def _update_pi_last_chat_ts(
        self,
        session_id: str,
        events: list[dict[str, Any]],
        *,
        session_path: Any,
    ) -> None:
        _sv(self)._message_history.service(self).update_pi_last_chat_ts(
            session_id,
            events,
            session_path=session_path,
        )

    def _ensure_pi_chat_index(
        self,
        session_id: str,
        *,
        min_events: int,
        before: int,
    ) -> tuple[list[dict[str, Any]], int, bool, int, dict[str, Any]]:
        return _sv(self)._message_history.service(self).ensure_pi_chat_index(
            session_id,
            min_events=min_events,
            before=before,
        )

    def _ensure_chat_index(
        self,
        session_id: str,
        *,
        min_events: int,
        before: int,
    ) -> tuple[list[dict[str, Any]], int, bool, int, dict[str, Any] | None]:
        return _sv(self)._message_history.service(self).ensure_chat_index(
            session_id,
            min_events=min_events,
            before=before,
        )

    def mark_log_delta(
        self,
        session_id: str,
        *,
        objs: list[dict[str, Any]],
        new_off: int,
    ) -> None:
        _sv(self)._message_history.service(self).mark_log_delta(
            session_id,
            objs=objs,
            new_off=new_off,
        )

    def idle_from_log(self, session_id: str) -> bool:
        return _sv(self)._message_history.service(self).idle_from_log(session_id)

    def get_messages_page(
        self,
        session_id: str,
        *,
        offset: int,
        init: bool,
        limit: int,
        before: int,
        view: str = "conversation",
    ) -> dict[str, Any]:
        return _sv(self)._message_history.service(self).get_messages_page(
            session_id,
            offset=offset,
            init=init,
            limit=limit,
            before=before,
            view=view,
        )

    def _sock_call(
        self,
        sock_path: Any,
        req: dict[str, Any],
        timeout_s: float = 2.0,
    ) -> dict[str, Any]:
        return _sv(self)._session_transport.service(self).sock_call(
            sock_path,
            req,
            timeout_s=timeout_s,
        )

    def _kill_session_via_pids(self, s: Any) -> bool:
        return _sv(self)._session_transport.service(self).kill_session_via_pids(s)

    def kill_session(self, session_id: str) -> bool:
        return _sv(self)._session_transport.service(self).kill_session(session_id)

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
        return _sv(self)._session_control.service(self).spawn_web_session(
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

    def delete_session(self, session_id: str) -> bool:
        runtime_id = self._runtime_session_id_for_identifier(session_id)
        if runtime_id is None:
            ref = self._page_state_ref_for_session_id(session_id)
            if ref is None:
                return False
            backend, durable_id = ref
            self._hide_session_identity_values(
                session_id,
                durable_id,
                durable_id if backend == "pi" else None,
                backend,
            )
            self._delete_durable_session_record(ref)
            self._clear_deleted_session_state(session_id)
            return True
        with self._lock:
            s = self._sessions.get(runtime_id)
        if not s:
            return False
        ok = self.kill_session(runtime_id)
        if ok:
            self._hide_session_identity(s)
            self.files_clear(runtime_id)
            self._clear_deleted_session_state(runtime_id)
            with self._lock:
                self._sessions.pop(runtime_id, None)
        return ok

    def send(self, session_id: str, text: str) -> dict[str, Any]:
        return _sv(self)._session_control.service(self).send(session_id, text)

    def enqueue(self, session_id: str, text: str) -> dict[str, Any]:
        return _sv(self)._session_control.service(self).enqueue(session_id, text)

    def queue_list(self, session_id: str) -> list[str]:
        return _sv(self)._session_control.service(self).queue_list(session_id)

    def queue_delete(self, session_id: str, index: int) -> dict[str, Any]:
        return _sv(self)._session_control.service(self).queue_delete(session_id, int(index))

    def queue_update(self, session_id: str, index: int, text: str) -> dict[str, Any]:
        return _sv(self)._session_control.service(self).queue_update(
            session_id,
            int(index),
            text,
        )

    def get_state(self, session_id: str) -> dict[str, Any]:
        return _sv(self)._session_transport.service(self).get_state(session_id)

    def get_ui_state(self, session_id: str) -> dict[str, Any]:
        sv = _sv(self)
        return sv._pi_ui_bridge.get_ui_state(sv, self, session_id)

    def get_session_commands(self, session_id: str) -> dict[str, Any]:
        sv = _sv(self)
        return sv._pi_ui_bridge.get_session_commands(sv, self, session_id)

    def submit_ui_response(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        sv = _sv(self)
        return sv._pi_ui_bridge.submit_ui_response(sv, self, session_id, payload)

    def get_tail(self, session_id: str) -> str:
        return _sv(self)._session_transport.service(self).get_tail(session_id)

    def inject_keys(self, session_id: str, seq: str) -> dict[str, Any]:
        return _sv(self)._session_transport.service(self).inject_keys(session_id, seq)

    def mark_turn_complete(self, session_id: str, payload: dict[str, Any]) -> None:
        return
