from __future__ import annotations

from typing import Any

from .manager_delegates_shared import _instance_override, _method_override, _sv


class SessionManagerStateDelegates:
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
            ref = key if isinstance(key, tuple) and len(key) == 2 else self.page_state_ref_for_session_id(str(key))
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
            ref = key if isinstance(key, tuple) and len(key) == 2 else self.page_state_ref_for_session_id(str(key))
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

    def reset_log_caches(self, s: Any, *, meta_log_off: int) -> None:
        _sv(self).api.session_lifecycle.service(self).reset_log_caches(s, meta_log_off=meta_log_off)

    def _reset_log_caches(self, s: Any, *, meta_log_off: int) -> None:
        self.reset_log_caches(s, meta_log_off=meta_log_off)

    def session_source_changed(self, s: Any, *, log_path: Any, session_path: Any) -> bool:
        return _sv(self).api.session_lifecycle.service(self).session_source_changed(
            s,
            log_path=log_path,
            session_path=session_path,
        )

    def _session_source_changed(self, s: Any, *, log_path: Any, session_path: Any) -> bool:
        return self.session_source_changed(s, log_path=log_path, session_path=session_path)

    def claimed_pi_session_paths(self, *, exclude_sid: str = "") -> set[Any]:
        return _sv(self).api.session_lifecycle.service(self).claimed_pi_session_paths(exclude_sid=exclude_sid)

    def _claimed_pi_session_paths(self, *, exclude_sid: str = "") -> set[Any]:
        return self.claimed_pi_session_paths(exclude_sid=exclude_sid)

    def apply_session_source(self, s: Any, *, log_path: Any, session_path: Any) -> None:
        _sv(self).api.session_lifecycle.service(self).apply_session_source(
            s,
            log_path=log_path,
            session_path=session_path,
        )

    def _apply_session_source(self, s: Any, *, log_path: Any, session_path: Any) -> None:
        self.apply_session_source(s, log_path=log_path, session_path=session_path)

    def session_run_settings(
        self,
        *,
        meta: dict[str, Any],
        log_path: Any,
        backend: str | None = None,
        agent_backend: str | None = None,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        return _sv(self).api.session_lifecycle.service(self).session_run_settings(
            meta=meta,
            log_path=log_path,
            backend=backend,
            agent_backend=agent_backend,
        )

    def _session_run_settings(
        self,
        *,
        meta: dict[str, Any],
        log_path: Any,
        backend: str | None = None,
        agent_backend: str | None = None,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        return self.session_run_settings(
            meta=meta,
            log_path=log_path,
            backend=backend,
            agent_backend=agent_backend,
        )

    def session_transport(self, *, meta: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        transport = _sv(self).api.clean_optional_text(meta.get("transport"))
        tmux_session = _sv(self).api.clean_optional_text(meta.get("tmux_session"))
        tmux_window = _sv(self).api.clean_optional_text(meta.get("tmux_window"))
        if transport is None and (tmux_session is not None or tmux_window is not None):
            transport = "tmux"
        return transport, tmux_session, tmux_window

    def _session_transport(self, *, meta: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        return self.session_transport(meta=meta)

    def discover_existing_if_stale(self, *, force: bool = False) -> None:
        override = _instance_override(
            self,
            "_discover_existing_if_stale",
            SessionManagerStateDelegates._discover_existing_if_stale,
        )
        if override is not None:
            try:
                override(force=force)
            except TypeError:
                override()
            return
        now = _sv(self).api.time.time()
        with self._lock:
            last = float(getattr(self, "_last_discover_ts", 0.0))
        if (not force) and ((now - last) < _sv(self).api.DISCOVER_MIN_INTERVAL_SECONDS):
            return
        self.discover_existing(force=force, skip_invalid_sidecars=True)

    def _discover_existing_if_stale(self, *, force: bool = False) -> None:
        self.discover_existing_if_stale(force=force)

    def _sidecar_quarantine_signature(self, sock: Any) -> tuple[bool, int, int]:
        meta_path = sock.with_suffix(".json")
        try:
            st = meta_path.stat()
        except FileNotFoundError:
            return (False, 0, 0)
        return (True, int(st.st_mtime_ns), int(st.st_size))

    def sidecar_is_quarantined(self, sock: Any) -> bool:
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

    def _sidecar_is_quarantined(self, sock: Any) -> bool:
        return self.sidecar_is_quarantined(sock)

    def quarantine_sidecar(
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
            _sv(self).api.sys.stderr.write(
                f"error: discover: quarantining {reason} for {sock}: {type(exc).__name__}: {exc}\\n"
            )
            _sv(self).api.sys.stderr.flush()

    def _quarantine_sidecar(
        self,
        sock: Any,
        exc: BaseException,
        *,
        reason: str = "invalid sidecar",
        log: bool = True,
    ) -> None:
        self.quarantine_sidecar(sock, exc, reason=reason, log=log)

    def clear_sidecar_quarantine(self, sock: Any) -> None:
        bad_sidecars = getattr(self, "_bad_sidecars", None)
        if isinstance(bad_sidecars, dict):
            bad_sidecars.pop(str(sock), None)

    def _clear_sidecar_quarantine(self, sock: Any) -> None:
        self.clear_sidecar_quarantine(sock)

    def _load_harness(self) -> None:
        _sv(self).api.page_state.service(self).load_harness()

    def save_harness(self) -> None:
        override = _instance_override(
            self,
            "_save_harness",
            SessionManagerStateDelegates._save_harness,
        )
        if override is not None:
            override()
            return
        _sv(self).api.page_state.service(self).save_harness()

    def _save_harness(self) -> None:
        self.save_harness()

    def _load_aliases(self) -> None:
        self._sidebar_state_facade().load_aliases()

    def save_aliases(self) -> None:
        override = _instance_override(
            self,
            "_save_aliases",
            SessionManagerStateDelegates._save_aliases,
        )
        if override is not None:
            override()
            return
        self._persist_session_ui_state()

    def _save_aliases(self) -> None:
        self.save_aliases()

    def _load_sidebar_meta(self) -> None:
        self._sidebar_state_facade().load_sidebar_meta()

    def save_sidebar_meta(self) -> None:
        override = _instance_override(
            self,
            "_save_sidebar_meta",
            SessionManagerStateDelegates._save_sidebar_meta,
        )
        if override is not None:
            override()
            return
        self._persist_session_ui_state()

    def _save_sidebar_meta(self) -> None:
        self.save_sidebar_meta()

    def _load_hidden_sessions(self) -> None:
        self._sidebar_state_facade().load_hidden_sessions()

    def _save_hidden_sessions(self) -> None:
        self._persist_session_ui_state()

    def hidden_session_keys(
        self,
        session_id: str | None,
        thread_id: str | None,
        resume_session_id: str | None,
        backend: str | None,
    ) -> set[str]:
        override = _instance_override(
            self,
            "_hidden_session_keys",
            SessionManagerStateDelegates._hidden_session_keys,
        )
        if override is not None:
            return override(
                session_id,
                thread_id,
                resume_session_id,
                backend,
            )
        return self._sidebar_state_facade().hidden_session_keys(
            session_id,
            thread_id,
            resume_session_id,
            backend,
        )

    def _hidden_session_keys(
        self,
        session_id: str | None,
        thread_id: str | None,
        resume_session_id: str | None,
        backend: str | None,
    ) -> set[str]:
        return self.hidden_session_keys(
            session_id,
            thread_id,
            resume_session_id,
            backend,
        )

    def session_is_hidden(
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

    def _session_is_hidden(
        self,
        session_id: str | None,
        thread_id: str | None,
        resume_session_id: str | None,
        backend: str | None,
    ) -> bool:
        return self.session_is_hidden(
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

    def unhide_session(self, session_id: str) -> None:
        self._sidebar_state_facade().unhide_session(session_id)

    def _unhide_session(self, session_id: str) -> None:
        self.unhide_session(session_id)

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
        _sv(self).api.event_publish.service(_sv(self)).publish_sessions_invalidate(reason="alias_changed")
        return alias

    def alias_get(self, session_id: str) -> str:
        return self._sidebar_state_facade().alias_get(session_id)

    def alias_get_for_ref(self, ref: Any) -> str | None:
        return self._sidebar_state_facade().alias_get_for_ref(ref)

    def alias_clear(self, session_id: str) -> None:
        self._sidebar_state_facade().alias_clear(session_id)
        _sv(self).api.event_publish.service(_sv(self)).publish_sessions_invalidate(reason="alias_cleared")

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
        _sv(self).api.event_publish.service(_sv(self)).publish_sessions_invalidate(reason="sidebar_meta_changed")
        return payload

    def focus_set(self, session_id: str, focused: Any) -> bool:
        value = self._sidebar_state_facade().focus_set(session_id, focused)
        _sv(self).api.event_publish.service(_sv(self)).publish_sessions_invalidate(reason="focus_changed")
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
        _sv(self).api.event_publish.service(_sv(self)).publish_sessions_invalidate(reason="session_edited")
        return payload

    def clear_deleted_session_ui_state(self, session_id: str) -> None:
        override = _instance_override(
            self,
            "_clear_deleted_session_ui_state",
            SessionManagerStateDelegates._clear_deleted_session_ui_state,
        )
        if override is not None:
            override(session_id)
            return
        self._sidebar_state_facade().clear_deleted_session_ui_state(session_id)

    def _clear_deleted_session_ui_state(self, session_id: str) -> None:
        self.clear_deleted_session_ui_state(session_id)

    def clear_deleted_session_state(self, session_id: str) -> None:
        override = _instance_override(
            self,
            "_clear_deleted_session_state",
            SessionManagerStateDelegates._clear_deleted_session_state,
        )
        if override is not None:
            override(session_id)
            return
        self.clear_deleted_session_ui_state(session_id)
        _sv(self).api.page_state.service(self).clear_deleted_session_state(session_id)

    def _clear_deleted_session_state(self, session_id: str) -> None:
        self.clear_deleted_session_state(session_id)

    def _load_files(self) -> None:
        _sv(self).api.page_state.service(self).load_files()

    def save_files(self) -> None:
        override = _instance_override(
            self,
            "_save_files",
            SessionManagerStateDelegates._save_files,
        )
        if override is not None:
            override()
            return
        _sv(self).api.page_state.service(self).save_files()

    def _save_files(self) -> None:
        self.save_files()

    def _load_queues(self) -> None:
        _sv(self).api.page_state.service(self).load_queues()

    def save_queues(self) -> None:
        override = _instance_override(
            self,
            "_save_queues",
            SessionManagerStateDelegates._save_queues,
        )
        if override is not None:
            override()
            return
        _sv(self).api.page_state.service(self).save_queues()

    def _save_queues(self) -> None:
        self.save_queues()

    def _load_recent_cwds(self) -> None:
        _sv(self).api.page_state.service(self).load_recent_cwds()

    def save_recent_cwds(self) -> None:
        override = _method_override(
            self,
            "_save_recent_cwds",
            SessionManagerStateDelegates._save_recent_cwds,
        )
        if override is not None:
            override()
            return
        _sv(self).api.page_state.service(self).save_recent_cwds()

    def _save_recent_cwds(self) -> None:
        self.save_recent_cwds()

    def _load_cwd_groups(self) -> None:
        _sv(self).api.page_state.service(self).load_cwd_groups()

    def save_cwd_groups(self) -> None:
        override = _method_override(
            self,
            "_save_cwd_groups",
            SessionManagerStateDelegates._save_cwd_groups,
        )
        if override is not None:
            override()
            return
        _sv(self).api.page_state.service(self).save_cwd_groups()

    def _save_cwd_groups(self) -> None:
        self.save_cwd_groups()

    def cwd_groups_get(self) -> dict[str, dict[str, Any]]:
        return _sv(self).api.page_state.service(self).cwd_groups_get()

    def _prune_stale_workspace_dirs(self) -> None:
        _sv(self).api.page_state.service(self).prune_stale_workspace_dirs()

    def _known_cwd_group_keys(self) -> set[str]:
        return _sv(self).api.page_state.service(self).known_cwd_group_keys()

    def cwd_group_set(
        self,
        cwd: str,
        label: str | None = None,
        collapsed: bool | None = None,
    ) -> tuple[str, dict[str, Any]]:
        return _sv(self).api.page_state.service(self).cwd_group_set(
            cwd,
            label=label,
            collapsed=collapsed,
        )

    def _remember_recent_cwd(self, cwd: Any, *, ts: Any = None) -> bool:
        return _sv(self).api.page_state.service(self).remember_recent_cwd(cwd, ts=ts)

    def _backfill_recent_cwds_from_logs(self) -> None:
        _sv(self).api.page_state.service(self).backfill_recent_cwds_from_logs()

    def recent_cwds(self, *, limit: int | None = None) -> list[str]:
        sv = _sv(self)
        return sv.api.page_state.service(self).recent_cwds(
            limit=sv.api.RECENT_CWD_MAX if limit is None else limit
        )

    def queue_len(self, session_id: str) -> int:
        return _sv(self).api.page_state.service(self).queue_len(session_id)

    def _queue_len(self, session_id: str) -> int:
        return self.queue_len(session_id)

    def queue_list_local(self, session_id: str) -> list[str]:
        return _sv(self).api.page_state.service(self).queue_list_local(session_id)

    def _queue_list_local(self, session_id: str) -> list[str]:
        return self.queue_list_local(session_id)

    def queue_enqueue_local(self, session_id: str, text: str) -> dict[str, Any]:
        return _sv(self).api.page_state.service(self).queue_enqueue_local(session_id, text)

    def _queue_enqueue_local(self, session_id: str, text: str) -> dict[str, Any]:
        return self.queue_enqueue_local(session_id, text)

    def queue_delete_local(self, session_id: str, index: int) -> dict[str, Any]:
        return _sv(self).api.page_state.service(self).queue_delete_local(session_id, index)

    def _queue_delete_local(self, session_id: str, index: int) -> dict[str, Any]:
        return self.queue_delete_local(session_id, index)

    def queue_update_local(
        self,
        session_id: str,
        index: int,
        text: str,
    ) -> dict[str, Any]:
        return _sv(self).api.page_state.service(self).queue_update_local(
            session_id,
            index,
            text,
        )

    def _queue_update_local(
        self,
        session_id: str,
        index: int,
        text: str,
    ) -> dict[str, Any]:
        return self.queue_update_local(
            session_id,
            index,
            text,
        )

    def _files_key_for_session(self, session_id: str) -> tuple[str, Any, Any]:
        return _sv(self).api.page_state.service(self).files_key_for_session(session_id)

    def files_get(self, session_id: str) -> list[str]:
        return _sv(self).api.page_state.service(self).files_get(session_id)

    def files_add(self, session_id: str, path: str) -> list[str]:
        return _sv(self).api.page_state.service(self).files_add(session_id, path)

    def files_clear(self, session_id: str) -> None:
        _sv(self).api.page_state.service(self).files_clear(session_id)

    def harness_get(self, session_id: str) -> dict[str, Any]:
        return _sv(self).api.page_state.service(self).harness_get(session_id)

    def harness_set(
        self,
        session_id: str,
        *,
        enabled: bool | None = None,
        request: str | None = None,
        cooldown_minutes: int | None = None,
        remaining_injections: int | None = None,
    ) -> dict[str, Any]:
        return _sv(self).api.page_state.service(self).harness_set(
            session_id,
            enabled=enabled,
            request=request,
            cooldown_minutes=cooldown_minutes,
            remaining_injections=remaining_injections,
        )

