from __future__ import annotations

import time
from pathlib import Path
from typing import Any


class RuntimeFacadeSessionMixin:
    def tmux_available(self) -> bool:
        return bool(self.api.tmux_available())

    def session_list_page_size(self) -> int:
        return int(self.api.SESSION_LIST_PAGE_SIZE)

    def session_list_group_page_size(self) -> int:
        return int(self.api.SESSION_LIST_GROUP_PAGE_SIZE)

    def session_list_recent_group_limit(self) -> int:
        return int(self.api.SESSION_LIST_RECENT_GROUP_LIMIT)

    def session_history_page_size(self) -> int:
        return int(self.api.SESSION_HISTORY_PAGE_SIZE)

    def record_metric(self, name: str, value: float) -> None:
        self.api.record_metric(name, value)

    def clean_harness_cooldown_minutes(self, value: Any) -> int:
        return int(self.api.clean_harness_cooldown_minutes(value))

    def clean_harness_remaining_injections(self, value: Any, *, allow_zero: bool) -> int | None:
        return self.api.clean_harness_remaining_injections(value, allow_zero=allow_zero)

    def session_live_payload(
        self,
        session_id: str,
        *,
        offset: int,
        live_offset: int,
        bridge_offset: int,
        requests_version: str | None,
    ) -> dict[str, Any]:
        return self.api.session_live_payload(
            self.manager,
            session_id,
            offset=offset,
            live_offset=live_offset,
            bridge_offset=bridge_offset,
            requests_version=requests_version,
        )

    def session_workspace_payload(self, session_id: str) -> dict[str, Any]:
        return self.api.session_payloads.service(
            self.runtime,
            self.manager,
        ).session_workspace_payload(session_id)

    def session_details_payload(self, session_id: str) -> dict[str, Any]:
        return self.api.session_payloads.service(
            self.runtime,
            self.manager,
        ).session_details_payload(session_id)

    def session_diagnostics_payload(self, session_id: str) -> dict[str, Any]:
        from .sessions import payloads as _session_payloads

        self.manager.refresh_session_meta(session_id, strict=False)
        session = self.manager.get_session(session_id)
        if not session:
            raise KeyError("unknown session")
        state = self.api.session_display.service(self.runtime).validated_session_state(self.manager.get_state(session_id))
        return _session_payloads.service(self.runtime, self.manager).session_diagnostics_payload(
            session_id,
            session,
            state,
        )

    def session_queue_payload(self, session_id: str) -> dict[str, Any]:
        queue = self.manager.queue_list(session_id)
        return {"ok": True, "queue": queue}

    def session_ui_state_payload(self, session_id: str) -> dict[str, Any]:
        return self.manager.get_ui_state(session_id)

    def session_commands_payload(self, session_id: str) -> dict[str, Any]:
        return self.manager.get_session_commands(session_id)

    def session_messages_payload(
        self,
        session_id: str,
        *,
        offset: int,
        init: bool,
        limit: int,
        before: int,
    ) -> dict[str, Any]:
        t0_meta = time.perf_counter()
        self.manager.refresh_session_meta(session_id, strict=False)
        dt_meta_ms = (time.perf_counter() - t0_meta) * 1000.0
        session = self.manager.get_session(session_id)
        historical_row = self.api.session_listing.service(self.runtime).historical_session_row(session_id)
        if (not session) and historical_row is None:
            raise KeyError("unknown session")
        payload = self.manager.get_messages_page(
            session_id,
            offset=offset,
            init=init,
            limit=limit,
            before=before,
        )
        if isinstance(payload.get("diag"), dict) and session is not None and session.backend != "pi":
            payload["diag"]["meta_refresh_ms"] = round(dt_meta_ms, 3)
        return payload

    def session_tail_payload(self, session_id: str) -> dict[str, Any]:
        return {"tail": self.manager.get_tail(session_id)}

    def session_harness_payload(self, session_id: str) -> dict[str, Any]:
        cfg = self.manager.harness_get(session_id)
        return {"ok": True, **cfg}

    def _normalize_git_list(self, rows: list[str]) -> list[str]:
        out: list[str] = []
        for row in rows:
            text = row.strip()
            if not text:
                continue
            out.append(text)
            if len(out) >= self.api.GIT_CHANGED_FILES_MAX:
                break
        return out

    def session_git_changed_files_payload(self, session_id: str) -> dict[str, Any]:
        self.manager.refresh_session_meta(session_id, strict=False)
        session = self.manager.get_session(session_id)
        if not session:
            raise KeyError("unknown session")
        cwd = self.api.safe_expanduser(Path(session.cwd))
        if not cwd.is_absolute():
            cwd = cwd.resolve()
        self.api.require_git_repo(cwd)
        unstaged = self.api.run_git(
            cwd,
            ["diff", "--name-only"],
            timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=64 * 1024,
        ).splitlines()
        staged = self.api.run_git(
            cwd,
            ["diff", "--name-only", "--cached"],
            timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=64 * 1024,
        ).splitlines()
        unstaged_numstat = self.api.run_git(
            cwd,
            ["diff", "--numstat"],
            timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=128 * 1024,
        )
        staged_numstat = self.api.run_git(
            cwd,
            ["diff", "--numstat", "--cached"],
            timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=128 * 1024,
        )
        unstaged2 = self._normalize_git_list(unstaged)
        staged2 = self._normalize_git_list(staged)
        seen: set[str] = set()
        merged: list[str] = []
        for row in [*unstaged2, *staged2]:
            if row in seen:
                continue
            seen.add(row)
            merged.append(row)
        stats = self.api.spawn_utils.service(self.runtime).parse_git_numstat(
            unstaged_numstat
        )
        for path_key, vals in self.api.spawn_utils.service(
            self.runtime
        ).parse_git_numstat(staged_numstat).items():
            prev = stats.get(path_key)
            if prev is None:
                stats[path_key] = vals
                continue
            add_prev = prev.get("additions")
            del_prev = prev.get("deletions")
            add_new = vals.get("additions")
            del_new = vals.get("deletions")
            prev["additions"] = (
                None if add_prev is None or add_new is None else int(add_prev) + int(add_new)
            )
            prev["deletions"] = (
                None if del_prev is None or del_new is None else int(del_prev) + int(del_new)
            )
        entries: list[dict[str, Any]] = []
        for path_key in merged:
            vals = stats.get(path_key, {})
            entries.append(
                {
                    "path": path_key,
                    "additions": vals.get("additions"),
                    "deletions": vals.get("deletions"),
                    "changed": True,
                }
            )
        return {
            "ok": True,
            "cwd": str(cwd),
            "files": merged,
            "entries": entries,
            "unstaged": unstaged2,
            "staged": staged2,
        }

    def session_git_diff_payload(
        self,
        session_id: str,
        *,
        rel_path: str,
        staged: bool,
    ) -> dict[str, Any]:
        self.manager.refresh_session_meta(session_id, strict=False)
        session = self.manager.get_session(session_id)
        if not session:
            raise KeyError("unknown session")
        cwd = self.api.safe_expanduser(Path(session.cwd))
        if not cwd.is_absolute():
            cwd = cwd.resolve()
        self.api.require_git_repo(cwd)
        _target, _repo_root, rel = self.api.resolve_git_path(cwd, rel_path)
        args = ["diff", "-U3"]
        if staged:
            args.append("--cached")
        args.extend(["--", rel])
        diff = self.api.run_git(
            cwd,
            args,
            timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=self.api.GIT_DIFF_MAX_BYTES,
        )
        return {
            "ok": True,
            "cwd": str(cwd),
            "path": rel,
            "staged": staged,
            "diff": diff,
        }

    def session_git_file_versions_payload(
        self,
        session_id: str,
        *,
        rel_path: str,
    ) -> dict[str, Any]:
        self.manager.refresh_session_meta(session_id, strict=False)
        session = self.manager.get_session(session_id)
        if not session:
            raise KeyError("unknown session")
        cwd = self.api.safe_expanduser(Path(session.cwd))
        if not cwd.is_absolute():
            cwd = cwd.resolve()
        self.api.require_git_repo(cwd)
        path_obj, _repo_root, rel = self.api.resolve_git_path(cwd, rel_path)
        current_text = ""
        current_size = 0
        current_exists = bool(path_obj.exists() and path_obj.is_file())
        if current_exists:
            current_text, current_size = self.api.read_text_file_strict(
                path_obj,
                max_bytes=self.api.FILE_READ_MAX_BYTES,
            )
        try:
            self.manager.files_add(session_id, str(path_obj))
        except KeyError:
            pass
        base_exists = False
        base_text = ""
        try:
            base_text = self.api.run_git(
                cwd,
                ["show", f"HEAD:{rel}"],
                timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
                max_bytes=self.api.FILE_READ_MAX_BYTES,
            )
            base_exists = True
        except RuntimeError:
            base_exists = False
            base_text = ""
        return {
            "ok": True,
            "cwd": str(cwd),
            "path": rel,
            "abs_path": str(path_obj),
            "current_exists": current_exists,
            "current_size": int(current_size),
            "current_text": current_text,
            "base_exists": base_exists,
            "base_text": base_text,
        }

    def sessions_bootstrap_payload(
        self,
        *,
        refresh_pi_models: bool,
    ) -> dict[str, Any]:
        from .sessions import creation as _session_creation

        return {
            "recent_cwds": self.manager.recent_cwds(),
            "cwd_groups": self.manager.cwd_groups_get(),
            "new_session_defaults": _session_creation.read_new_session_defaults(
                self.runtime,
                page_state_db=getattr(self.manager, "_page_state_db", None),
                refresh_pi_models=refresh_pi_models,
            ),
            "tmux_available": self.tmux_available(),
        }

    def sessions_list_payload(
        self,
        *,
        group_key: str | None,
        offset: int,
        limit: int,
        group_offset: int,
        group_limit: int,
    ) -> dict[str, Any]:
        return self.api.session_listing.service(self.runtime).session_list_payload(
            self.manager.list_sessions(),
            group_key=group_key,
            offset=offset,
            limit=limit,
            group_offset=group_offset,
            group_limit=group_limit,
        )

    def resume_candidates_payload(
        self,
        *,
        cwd_raw: str,
        backend_raw: str,
        offset_raw: str,
        limit_raw: str,
        agent_backend_raw: str,
    ) -> dict[str, Any]:
        from .runtime_facade import FacadeRequestError

        try:
            agent_backend = self.api.normalize_agent_backend(
                agent_backend_raw,
                default=self.api.DEFAULT_AGENT_BACKEND,
            )
        except ValueError as exc:
            raise FacadeRequestError(str(exc)) from exc

        try:
            cwd_path = self.api.resolve_dir_target(str(cwd_raw), field_name="cwd")
        except ValueError as exc:
            raise FacadeRequestError(str(exc), field="cwd") from exc

        try:
            backend = self.api.session_settings.service(self.runtime).normalize_requested_backend(backend_raw)
        except ValueError as exc:
            raise FacadeRequestError(str(exc), field="backend") from exc

        try:
            offset = max(0, int(offset_raw))
        except ValueError as exc:
            raise FacadeRequestError("offset must be an integer", field="offset") from exc

        try:
            limit = max(1, min(100, int(limit_raw)))
        except ValueError as exc:
            raise FacadeRequestError("limit must be an integer", field="limit") from exc

        info = self.api.describe_session_cwd(cwd_path)
        all_rows = (
            self.api.resume_candidates.service(self.runtime).list_resume_candidates_for_cwd(
                info["cwd"],
                backend=backend,
                limit=100000,
            )
            if info["exists"]
            else []
        )
        rows = all_rows[offset : offset + limit]
        remaining = max(0, len(all_rows) - (offset + len(rows)))
        for row in rows:
            sid = row.get("session_id")
            alias = self.manager.alias_get(sid) if isinstance(sid, str) and sid else ""
            preview = ""
            log_path_raw = row.get("log_path")
            session_path_raw = row.get("session_path")
            if isinstance(log_path_raw, str) and log_path_raw:
                preview = self.api.session_listing.service(self.runtime).first_user_message_preview_from_log(Path(log_path_raw))
            elif isinstance(session_path_raw, str) and session_path_raw:
                preview = self.api.session_listing.service(self.runtime).first_user_message_preview_from_pi_session(Path(session_path_raw))
            row["alias"] = alias
            row["first_user_message"] = preview
        return {
            "ok": True,
            **info,
            "sessions": rows,
            "offset": offset,
            "limit": limit,
            "remaining": remaining,
            "agent_backend": agent_backend,
        }

    def metrics_payload(self) -> dict[str, Any]:
        return {"metrics": self.api.metrics_snapshot()}

    def parse_create_session_request(self, obj: dict[str, Any]) -> dict[str, Any]:
        from .sessions import creation as _session_creation

        return _session_creation.parse_create_session_request(self.runtime, obj)

    def cwd_group_set(
        self,
        *,
        cwd: Any,
        label: Any,
        collapsed: Any,
    ) -> tuple[str, dict[str, Any]]:
        return self.manager.cwd_group_set(cwd=cwd, label=label, collapsed=collapsed)

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        res = self.manager.spawn_web_session(
            cwd=payload["cwd"],
            args=payload["args"],
            resume_session_id=payload["resume_session_id"],
            worktree_branch=payload["worktree_branch"],
            model_provider=payload["model_provider"],
            preferred_auth_method=payload["preferred_auth_method"],
            model=payload["model"],
            reasoning_effort=payload["reasoning_effort"],
            service_tier=payload["service_tier"],
            create_in_tmux=payload["create_in_tmux"],
            backend=payload["backend"],
        )
        alias = self.manager.set_created_session_name(
            session_id=res.get("session_id"),
            runtime_id=res.get("runtime_id"),
            backend=res.get("backend") or payload["backend"],
            name=payload["name"],
        )
        focused = False
        focus_targets: list[str] = []
        for candidate in (res.get("session_id"), res.get("runtime_id")):
            if not isinstance(candidate, str):
                continue
            target = candidate.strip()
            if not target or target in focus_targets:
                continue
            focus_targets.append(target)
        for target in focus_targets:
            try:
                focused = bool(self.manager.focus_set(target, True))
                if focused:
                    break
            except (KeyError, ValueError):
                continue
        out = {"ok": True, **res, "focused": bool(focused)}
        if alias:
            out["alias"] = alias
        self.api.event_publish.service(self.runtime).publish_sessions_invalidate(reason="session_created")
        return out

    def delete_session(self, session_id: str) -> bool:
        deleted = bool(self.manager.delete_session(session_id))
        if deleted:
            self.api.event_publish.service(self.runtime).publish_sessions_invalidate(reason="session_deleted")
        return deleted

    def handoff_session(self, session_id: str) -> dict[str, Any]:
        res = self.manager.handoff_session(session_id)
        self.api.event_publish.service(self.runtime).publish_sessions_invalidate(reason="session_created")
        return {"ok": True, **res}

    def restart_session(self, session_id: str) -> dict[str, Any]:
        res = self.manager.restart_session(session_id)
        self.api.event_publish.service(self.runtime).publish_sessions_invalidate(reason="session_created")
        return {"ok": True, **res}

    def session_edit(self, session_id: str, obj: dict[str, Any]) -> dict[str, Any]:
        alias, sidebar_meta = self.manager.edit_session(
            session_id,
            name=obj.get("name"),
            priority_offset=obj.get("priority_offset"),
            snooze_until=obj.get("snooze_until"),
            dependency_session_id=obj.get("dependency_session_id"),
        )
        return {"ok": True, "alias": alias, **sidebar_meta}

    def session_rename(self, session_id: str, *, name: str) -> dict[str, Any]:
        return {"ok": True, "alias": self.manager.alias_set(session_id, name)}

    def session_focus(self, session_id: str, *, focused: Any) -> dict[str, Any]:
        return {"ok": True, "focused": self.manager.focus_set(session_id, focused)}

    def session_send(self, session_id: str, *, text: str) -> dict[str, Any]:
        return self.manager.send(session_id, text)

    def session_enqueue(self, session_id: str, *, text: str) -> dict[str, Any]:
        return self.manager.enqueue(session_id, text)

    def session_queue_delete(self, session_id: str, *, index: int) -> dict[str, Any]:
        return self.manager.queue_delete(session_id, index)

    def session_queue_update(self, session_id: str, *, index: int, text: str) -> dict[str, Any]:
        return self.manager.queue_update(session_id, index, text)

    def session_submit_ui_response(self, session_id: str, obj: dict[str, Any]) -> dict[str, Any]:
        self.manager.submit_ui_response(session_id, obj)
        durable_session_id = self.manager.durable_session_id_for_identifier(session_id) or session_id
        runtime_id = self.manager.runtime_session_id_for_identifier(session_id)
        self.api.event_publish.service(self.runtime).publish_session_workspace_invalidate(
            durable_session_id,
            runtime_id=runtime_id,
            reason="ui_response",
        )
        return {"ok": True}

    def session_set_model(
        self,
        session_id: str,
        *,
        model: str,
        provider: str | None = None,
    ) -> dict[str, Any]:
        payload = self.manager.set_session_model(
            session_id,
            model=model,
            provider=provider,
        )
        durable_session_id = self.manager.durable_session_id_for_identifier(session_id) or session_id
        runtime_id = self.manager.runtime_session_id_for_identifier(session_id)
        self.api.event_publish.service(self.runtime).publish_session_live_invalidate(
            durable_session_id,
            runtime_id=runtime_id,
            reason="model_switched",
        )
        self.api.event_publish.service(self.runtime).publish_session_workspace_invalidate(
            durable_session_id,
            runtime_id=runtime_id,
            reason="model_switched",
        )
        self.api.event_publish.service(self.runtime).publish_sessions_invalidate(
            reason="model_switched",
        )
        return payload

    def session_harness_set(
        self,
        session_id: str,
        *,
        enabled: bool | None,
        request: str | None,
        cooldown_minutes: int | None,
        remaining_injections: int | None,
    ) -> dict[str, Any]:
        cfg = self.manager.harness_set(
            session_id,
            enabled=enabled,
            request=request,
            cooldown_minutes=cooldown_minutes,
            remaining_injections=remaining_injections,
        )
        return {"ok": True, **cfg}

    def session_interrupt(self, session_id: str) -> dict[str, Any]:
        resp = self.manager.inject_keys(session_id, "\\x1b")
        durable_session_id = self.manager.durable_session_id_for_identifier(session_id) or session_id
        runtime_id = self.manager.runtime_session_id_for_identifier(session_id)
        self.api.event_publish.service(self.runtime).publish_session_live_invalidate(
            durable_session_id,
            runtime_id=runtime_id,
            reason="interrupt",
        )
        return {"ok": True, "broker": resp}
