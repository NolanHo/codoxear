from __future__ import annotations

from typing import Any

from .manager_delegates_shared import _sv


class SessionManagerRuntimeDelegates:
    def _session_display_name(self, session_id: str) -> str:
        return _sv(self).api.session_background.service(self).session_display_name(session_id)

    def _observe_rollout_delta(
        self,
        session_id: str,
        *,
        objs: list[dict[str, Any]],
        new_off: int,
    ) -> None:
        _sv(self).api.session_background.service(self).observe_rollout_delta(
            session_id,
            objs=objs,
            new_off=new_off,
        )

    def _voice_push_scan_loop(self) -> None:
        _sv(self).api.session_background.service(self).voice_push_scan_loop()

    def _voice_push_scan_sweep(self) -> None:
        _sv(self).api.session_background.service(self).voice_push_scan_sweep()

    def _harness_loop(self) -> None:
        _sv(self).api.session_background.service(self).harness_loop()

    def _harness_sweep(self) -> None:
        _sv(self).api.session_background.service(self).harness_sweep()

    def _queue_loop(self) -> None:
        _sv(self).api.session_background.service(self).queue_loop()

    def maybe_drain_session_queue(
        self,
        session_id: str,
        *,
        now_ts: float | None = None,
    ) -> bool:
        return _sv(self).api.session_background.service(self).maybe_drain_session_queue(
            session_id,
            now_ts=now_ts,
        )

    def _maybe_drain_session_queue(
        self,
        session_id: str,
        *,
        now_ts: float | None = None,
    ) -> bool:
        return self.maybe_drain_session_queue(session_id, now_ts=now_ts)

    def _queue_sweep(self) -> None:
        _sv(self).api.session_background.service(self).queue_sweep()

    def _discover_existing(
        self,
        *,
        force: bool = False,
        skip_invalid_sidecars: bool = False,
    ) -> None:
        _sv(self).api.session_catalog.service(self).discover_existing(
            force=force,
            skip_invalid_sidecars=skip_invalid_sidecars,
        )

    def _refresh_session_state(
        self,
        session_id: str,
        sock_path: Any,
        timeout_s: float = 0.4,
    ) -> tuple[bool, BaseException | None]:
        return _sv(self).api.session_catalog.service(self).refresh_session_state(
            session_id,
            sock_path,
            timeout_s=timeout_s,
        )

    def _prune_dead_sessions(self) -> None:
        _sv(self).api.session_catalog.service(self).prune_dead_sessions()

    def _update_meta_counters(self) -> None:
        _sv(self).api.session_background.service(self).update_meta_counters()

    def list_sessions(self) -> list[dict[str, Any]]:
        return _sv(self).api.session_catalog.service(self).list_sessions()

    def get_session(self, session_id: str):
        return _sv(self).api.session_catalog.service(self).get_session(session_id)

    def refresh_session_meta(self, session_id: str, *, strict: bool = True) -> None:
        _sv(self).api.session_catalog.service(self).refresh_session_meta(
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
        _sv(self).api.message_history.service(self).set_chat_index_snapshot(
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
        _sv(self).api.message_history.service(self).append_chat_events(
            session_id,
            new_events,
            new_off=new_off,
            latest_token=latest_token,
        )

    def _attach_notification_texts(
        self,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return _sv(self).api.message_history.service(self).attach_notification_texts(events)

    def _update_pi_last_chat_ts(
        self,
        session_id: str,
        events: list[dict[str, Any]],
        *,
        session_path: Any,
    ) -> None:
        _sv(self).api.message_history.service(self).update_pi_last_chat_ts(
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
        return _sv(self).api.message_history.service(self).ensure_pi_chat_index(
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
        return _sv(self).api.message_history.service(self).ensure_chat_index(
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
        _sv(self).api.message_history.service(self).mark_log_delta(
            session_id,
            objs=objs,
            new_off=new_off,
        )

    def idle_from_log(self, session_id: str) -> bool:
        return _sv(self).api.message_history.service(self).idle_from_log(session_id)

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
        return _sv(self).api.message_history.service(self).get_messages_page(
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
        return _sv(self).api.session_transport.service(self).sock_call(
            sock_path,
            req,
            timeout_s=timeout_s,
        )

    def _kill_session_via_pids(self, s: Any) -> bool:
        return _sv(self).api.session_transport.service(self).kill_session_via_pids(s)

    def kill_session(self, session_id: str) -> bool:
        return _sv(self).api.session_transport.service(self).kill_session(session_id)

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
        return _sv(self).api.session_control.service(self).spawn_web_session(
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
        runtime_id = self.runtime_session_id_for_identifier(session_id)
        if runtime_id is None:
            ref = self.page_state_ref_for_session_id(session_id)
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
        return _sv(self).api.session_control.service(self).send(session_id, text)

    def enqueue(self, session_id: str, text: str) -> dict[str, Any]:
        return _sv(self).api.session_control.service(self).enqueue(session_id, text)

    def queue_list(self, session_id: str) -> list[str]:
        return _sv(self).api.session_control.service(self).queue_list(session_id)

    def queue_delete(self, session_id: str, index: int) -> dict[str, Any]:
        return _sv(self).api.session_control.service(self).queue_delete(session_id, int(index))

    def queue_update(self, session_id: str, index: int, text: str) -> dict[str, Any]:
        return _sv(self).api.session_control.service(self).queue_update(
            session_id,
            int(index),
            text,
        )

    def get_state(self, session_id: str) -> dict[str, Any]:
        return _sv(self).api.session_transport.service(self).get_state(session_id)

    def resolve_pi_bridge_session(
        self,
        session_id: str,
        *,
        unsupported_message: str,
    ) -> tuple[str, Any]:
        runtime_id = self.runtime_session_id_for_identifier(session_id)
        if runtime_id is None:
            raise KeyError("unknown session")
        self.refresh_session_meta(runtime_id, strict=False)
        session = self.get_session(runtime_id)
        if session is None:
            raise KeyError("unknown session")
        if session.backend != "pi":
            raise ValueError(unsupported_message)
        return runtime_id, session

    def sock_call(
        self,
        sock_path: Any,
        req: dict[str, Any],
        timeout_s: float = 2.0,
    ) -> dict[str, Any]:
        return self._sock_call(sock_path, req, timeout_s=timeout_s)

    def discard_runtime_session(
        self,
        runtime_id: str,
        *,
        sock_path: Any | None = None,
    ) -> None:
        with self._lock:
            self._sessions.pop(runtime_id, None)
        self._clear_deleted_session_state(runtime_id)
        if sock_path is None:
            return
        sv = _sv(self)
        sv.api.unlink_quiet(sock_path)
        sv.api.unlink_quiet(sock_path.with_suffix(".json"))

    def pi_commands_cache_get(
        self,
        runtime_id: str,
        *,
        thread_id: str | None,
        session_path_key: str | None,
        now_ts: float,
    ) -> list[dict[str, Any]] | None:
        ttl = _sv(self).api.PI_COMMANDS_CACHE_TTL_SECONDS
        with self._lock:
            cache = getattr(self, "_pi_commands_cache", None)
            cached = cache.get(runtime_id) if isinstance(cache, dict) else None
        if not isinstance(cached, dict):
            return None
        cached_ts = cached.get("ts")
        if not isinstance(cached_ts, (int, float)) or (now_ts - float(cached_ts)) >= ttl:
            return None
        if cached.get("thread_id") != thread_id or cached.get("session_path") != session_path_key:
            return None
        commands = cached.get("commands")
        if not isinstance(commands, list):
            return None
        return list(commands)

    def pi_commands_cache_put(
        self,
        runtime_id: str,
        *,
        thread_id: str | None,
        session_path_key: str | None,
        commands: list[dict[str, Any]],
        now_ts: float,
    ) -> None:
        with self._lock:
            cache = getattr(self, "_pi_commands_cache", None)
            if not isinstance(cache, dict):
                self._pi_commands_cache = {}
                cache = self._pi_commands_cache
            cache[runtime_id] = {
                "ts": now_ts,
                "thread_id": thread_id,
                "session_path": session_path_key,
                "commands": list(commands),
            }

    def voice_delivery_available(self) -> bool:
        return getattr(self, "_voice_push", None) is not None

    def voice_observe_messages(
        self,
        *,
        session_id: str,
        session_display_name: str,
        messages: list[Any],
    ) -> bool:
        voice_push = getattr(self, "_voice_push", None)
        if voice_push is None:
            return False
        voice_push.observe_messages(
            session_id=session_id,
            session_display_name=session_display_name,
            messages=messages,
        )
        return True

    def voice_notification_text_for_message(self, message_id: str) -> str | None:
        voice_push = getattr(self, "_voice_push", None)
        if voice_push is None:
            return None
        text = voice_push.notification_text_for_message(message_id)
        return text if isinstance(text, str) and text else None

    def voice_settings_snapshot(self) -> dict[str, Any]:
        return self._voice_push.settings_snapshot()

    def voice_subscriptions_snapshot(self) -> dict[str, Any]:
        return self._voice_push.subscriptions_snapshot()

    def voice_notification_state_for_message(self, message_id: str) -> dict[str, Any] | None:
        return self._voice_push.notification_state_for_message(message_id)

    def voice_notification_feed_since(self, since_ts: float) -> list[dict[str, Any]]:
        return self._voice_push.notification_feed_since(since_ts)

    def voice_playlist_bytes(self) -> bytes:
        return self._voice_push.playlist_bytes()

    def voice_segment_bytes(self, segment_name: str) -> bytes:
        segment_path = self._voice_push.segment_path(segment_name)
        return segment_path.read_bytes()

    def voice_set_settings(self, obj: dict[str, Any]) -> dict[str, Any]:
        return self._voice_push.set_settings(obj)

    def voice_upsert_subscription(
        self,
        *,
        subscription: Any,
        user_agent: str,
        device_label: str,
        device_class: str,
    ) -> dict[str, Any]:
        return self._voice_push.upsert_subscription(
            subscription=subscription,
            user_agent=user_agent,
            device_label=device_label,
            device_class=device_class,
        )

    def voice_toggle_subscription(self, *, endpoint: str, enabled: bool) -> dict[str, Any]:
        return self._voice_push.toggle_subscription(endpoint=endpoint, enabled=enabled)

    def voice_send_test_push(self, *, session_display_name: str) -> dict[str, Any]:
        return self._voice_push.send_test_push_notification(
            session_display_name=session_display_name,
        )

    def voice_listener_heartbeat(self, *, client_id: str, enabled: bool) -> dict[str, Any]:
        return self._voice_push.listener_heartbeat(client_id=client_id, enabled=enabled)

    def voice_enqueue_test_announcement(self, *, session_display_name: str) -> dict[str, Any]:
        return self._voice_push.enqueue_test_announcement(
            session_display_name=session_display_name,
        )

    def get_ui_state(self, session_id: str) -> dict[str, Any]:
        sv = _sv(self)
        return sv.api.pi_ui_bridge.get_ui_state(sv, self, session_id)

    def get_session_commands(self, session_id: str) -> dict[str, Any]:
        sv = _sv(self)
        return sv.api.pi_ui_bridge.get_session_commands(sv, self, session_id)

    def submit_ui_response(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        sv = _sv(self)
        return sv.api.pi_ui_bridge.submit_ui_response(sv, self, session_id, payload)

    def get_tail(self, session_id: str) -> str:
        return _sv(self).api.session_transport.service(self).get_tail(session_id)

    def inject_keys(self, session_id: str, seq: str) -> dict[str, Any]:
        return _sv(self).api.session_transport.service(self).inject_keys(session_id, seq)

    def mark_turn_complete(self, session_id: str, payload: dict[str, Any]) -> None:
        return
