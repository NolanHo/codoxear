from __future__ import annotations

import time
import urllib.parse
from pathlib import Path
from typing import Any

from ...runtime import ServerRuntime
from ...runtime_facade import build_runtime_facade
from ...sessions import creation as _session_creation


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    facade = build_runtime_facade(runtime)

    if path == "/api/sessions/bootstrap":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        qs = urllib.parse.parse_qs(u.query)
        refresh_pi_models = (qs.get("refresh_pi_models") or ["0"])[0] == "1"
        facade.json_response(
            handler,
            200,
            {
                "recent_cwds": facade.manager.recent_cwds(),
                "cwd_groups": facade.manager.cwd_groups_get(),
                "new_session_defaults": _session_creation.read_new_session_defaults(
                    runtime,
                    page_state_db=getattr(facade.manager, "_page_state_db", None),
                    refresh_pi_models=refresh_pi_models,
                ),
                "tmux_available": runtime.api.tmux_available(),
            },
        )
        return True

    if path == "/api/sessions":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        t0 = time.perf_counter()
        qs = urllib.parse.parse_qs(u.query)
        group_key_q = qs.get("group_key")
        group_key = group_key_q[0] if group_key_q else None
        offset = max(0, int(qs.get("offset", ["0"])[0] or "0"))
        limit_default = runtime.api.SESSION_LIST_PAGE_SIZE
        if group_key is not None:
            limit_default = runtime.api.SESSION_LIST_GROUP_PAGE_SIZE
        limit = max(
            1,
            min(200, int(qs.get("limit", [str(limit_default)])[0] or str(limit_default))),
        )
        group_offset = max(0, int(qs.get("group_offset", ["0"])[0] or "0"))
        group_limit = max(
            1,
            min(
                20,
                int(
                    qs.get("group_limit", [str(runtime.api.SESSION_LIST_RECENT_GROUP_LIMIT)])[0]
                    or str(runtime.api.SESSION_LIST_RECENT_GROUP_LIMIT)
                ),
            ),
        )
        payload = runtime.api.session_list_payload(
            facade.manager.list_sessions(),
            group_key=group_key,
            offset=offset,
            limit=limit,
            group_offset=group_offset,
            group_limit=group_limit,
        )
        dt_ms = (time.perf_counter() - t0) * 1000.0
        runtime.api.record_metric("api_sessions_ms", dt_ms)
        facade.json_response(handler, 200, payload)
        return True

    if path == "/api/session_resume_candidates":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        qs = urllib.parse.parse_qs(u.query)
        cwd_raw = qs.get("cwd", [""])[0]
        backend_raw = qs.get("backend", ["codex"])[0]
        offset_raw = qs.get("offset", ["0"])[0]
        limit_raw = qs.get("limit", ["20"])[0]
        try:
            agent_backend = runtime.api.normalize_agent_backend(
                qs.get("agent_backend", [""])[0],
                default=runtime.api.DEFAULT_AGENT_BACKEND,
            )
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        try:
            cwd_path = runtime.api.resolve_dir_target(str(cwd_raw), field_name="cwd")
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc), "field": "cwd"})
            return True
        try:
            backend = runtime.api.normalize_requested_backend(backend_raw)
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc), "field": "backend"})
            return True
        try:
            offset = max(0, int(offset_raw))
        except ValueError:
            facade.json_response(
                handler,
                400,
                {"error": "offset must be an integer", "field": "offset"},
            )
            return True
        try:
            limit = max(1, min(100, int(limit_raw)))
        except ValueError:
            facade.json_response(
                handler,
                400,
                {"error": "limit must be an integer", "field": "limit"},
            )
            return True
        info = runtime.api.describe_session_cwd(cwd_path)
        all_rows = (
            runtime.api.list_resume_candidates_for_cwd(info["cwd"], backend=backend, limit=100000)
            if info["exists"]
            else []
        )
        rows = all_rows[offset : offset + limit]
        remaining = max(0, len(all_rows) - (offset + len(rows)))
        for row in rows:
            sid = row.get("session_id")
            alias = facade.manager.alias_get(sid) if isinstance(sid, str) and sid else ""
            preview = ""
            log_path_raw = row.get("log_path")
            session_path_raw = row.get("session_path")
            if isinstance(log_path_raw, str) and log_path_raw:
                preview = runtime.api.first_user_message_preview_from_log(Path(log_path_raw))
            elif isinstance(session_path_raw, str) and session_path_raw:
                preview = runtime.api.first_user_message_preview_from_pi_session(Path(session_path_raw))
            row["alias"] = alias
            row["first_user_message"] = preview
        facade.json_response(
            handler,
            200,
            {
                "ok": True,
                **info,
                "sessions": rows,
                "offset": offset,
                "limit": limit,
                "remaining": remaining,
                "agent_backend": agent_backend,
            },
        )
        return True

    if path == "/api/metrics":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        facade.json_response(handler, 200, facade.metrics_payload())
        return True

    return False
