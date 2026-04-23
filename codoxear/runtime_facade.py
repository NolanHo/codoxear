from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime import ServerRuntime


@dataclass(slots=True)
class RuntimeFacade:
    runtime: ServerRuntime

    @property
    def api(self) -> Any:
        return self.runtime.api

    @property
    def manager(self) -> Any:
        return self.runtime.manager

    def require_auth(self, handler: Any) -> bool:
        return bool(self.api.require_auth(handler))

    def json_response(self, handler: Any, status: int, payload: dict[str, Any]) -> None:
        self.api.json_response(handler, status, payload)

    def match_session_route(self, path: str, suffix: str) -> str | None:
        return self.api.match_session_route(path, suffix)

    def poll_events(self, after_seq: int, *, timeout_s: float) -> Any:
        return self.api.EVENT_HUB.poll(after_seq, timeout_s=timeout_s)

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
        return self.api.session_workspace_payload(self.manager, session_id)

    def session_details_payload(self, session_id: str) -> dict[str, Any]:
        return self.api.session_details_payload(self.manager, session_id)

    def session_diagnostics_payload(self, session_id: str) -> dict[str, Any]:
        from .sessions import payloads as _session_payloads

        self.manager.refresh_session_meta(session_id, strict=False)
        session = self.manager.get_session(session_id)
        if not session:
            raise KeyError("unknown session")
        state = self.api.validated_session_state(self.manager.get_state(session_id))
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
        historical_row = self.api.historical_session_row(session_id)
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

    def sessions_bootstrap_payload(
        self,
        *,
        runtime: ServerRuntime,
        refresh_pi_models: bool,
    ) -> dict[str, Any]:
        from .sessions import creation as _session_creation

        return {
            "recent_cwds": self.manager.recent_cwds(),
            "cwd_groups": self.manager.cwd_groups_get(),
            "new_session_defaults": _session_creation.read_new_session_defaults(
                runtime,
                page_state_db=getattr(self.manager, "_page_state_db", None),
                refresh_pi_models=refresh_pi_models,
            ),
            "tmux_available": self.api.tmux_available(),
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
        return self.api.session_list_payload(
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
        agent_backend = self.api.normalize_agent_backend(
            agent_backend_raw,
            default=self.api.DEFAULT_AGENT_BACKEND,
        )
        cwd_path = self.api.resolve_dir_target(str(cwd_raw), field_name="cwd")
        backend = self.api.normalize_requested_backend(backend_raw)
        offset = max(0, int(offset_raw))
        limit = max(1, min(100, int(limit_raw)))
        info = self.api.describe_session_cwd(cwd_path)
        all_rows = (
            self.api.list_resume_candidates_for_cwd(
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
                preview = self.api.first_user_message_preview_from_log(Path(log_path_raw))
            elif isinstance(session_path_raw, str) and session_path_raw:
                preview = self.api.first_user_message_preview_from_pi_session(Path(session_path_raw))
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
        out = {"ok": True, **res}
        if alias:
            out["alias"] = alias
        self.api.publish_sessions_invalidate(reason="session_created")
        return out

    def delete_session(self, session_id: str) -> bool:
        deleted = bool(self.manager.delete_session(session_id))
        if deleted:
            self.api.publish_sessions_invalidate(reason="session_deleted")
        return deleted

    def handoff_session(self, session_id: str) -> dict[str, Any]:
        res = self.manager.handoff_session(session_id)
        self.api.publish_sessions_invalidate(reason="session_created")
        return {"ok": True, **res}

    def restart_session(self, session_id: str) -> dict[str, Any]:
        res = self.manager.restart_session(session_id)
        self.api.publish_sessions_invalidate(reason="session_created")
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
        durable_session_id = (
            self.manager._durable_session_id_for_identifier(session_id) or session_id
        )
        runtime_id = self.manager._runtime_session_id_for_identifier(session_id)
        self.api.publish_session_workspace_invalidate(
            durable_session_id,
            runtime_id=runtime_id,
            reason="ui_response",
        )
        return {"ok": True}

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
        durable_session_id = (
            self.manager._durable_session_id_for_identifier(session_id) or session_id
        )
        runtime_id = self.manager._runtime_session_id_for_identifier(session_id)
        self.api.publish_session_live_invalidate(
            durable_session_id,
            runtime_id=runtime_id,
            reason="interrupt",
        )
        return {"ok": True, "broker": resp}


def build_runtime_facade(runtime: ServerRuntime) -> RuntimeFacade:
    return RuntimeFacade(runtime)
