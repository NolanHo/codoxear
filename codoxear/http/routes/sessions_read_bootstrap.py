from __future__ import annotations

import time
import urllib.parse
from typing import Any

from ...runtime import ServerRuntime
from ...runtime_facade import FacadeRequestError, build_runtime_facade


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
            facade.sessions_bootstrap_payload(refresh_pi_models=refresh_pi_models),
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

        limit_default = facade.session_list_page_size()
        if group_key is not None:
            limit_default = facade.session_list_group_page_size()
        limit = max(
            1,
            min(200, int(qs.get("limit", [str(limit_default)])[0] or str(limit_default))),
        )

        group_offset = max(0, int(qs.get("group_offset", ["0"])[0] or "0"))
        group_limit_default = facade.session_list_recent_group_limit()
        group_limit = max(
            1,
            min(
                20,
                int(qs.get("group_limit", [str(group_limit_default)])[0] or str(group_limit_default)),
            ),
        )

        payload = facade.sessions_list_payload(
            group_key=group_key,
            offset=offset,
            limit=limit,
            group_offset=group_offset,
            group_limit=group_limit,
        )
        dt_ms = (time.perf_counter() - t0) * 1000.0
        facade.record_metric("api_sessions_ms", dt_ms)
        facade.json_response(handler, 200, payload)
        return True

    if path == "/api/session_resume_candidates":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        qs = urllib.parse.parse_qs(u.query)
        try:
            payload = facade.resume_candidates_payload(
                cwd_raw=qs.get("cwd", [""])[0],
                backend_raw=qs.get("backend", ["codex"])[0],
                offset_raw=qs.get("offset", ["0"])[0],
                limit_raw=qs.get("limit", ["20"])[0],
                agent_backend_raw=qs.get("agent_backend", [""])[0],
            )
        except FacadeRequestError as exc:
            error_payload: dict[str, Any] = {"error": str(exc)}
            if exc.field is not None:
                error_payload["field"] = exc.field
            facade.json_response(handler, 400, error_payload)
            return True

        facade.json_response(handler, 200, payload)
        return True

    if path == "/api/metrics":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        facade.json_response(handler, 200, facade.metrics_payload())
        return True

    return False
