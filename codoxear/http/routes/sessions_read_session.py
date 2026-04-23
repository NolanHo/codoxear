from __future__ import annotations

import time
import urllib.parse
from pathlib import Path
from typing import Any

from ...runtime import ServerRuntime
from . import sessions_read_common as _common


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    if path.startswith("/api/sessions/") and path.endswith("/live"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        qs = urllib.parse.parse_qs(u.query)
        offset_q = qs.get("offset")
        live_offset_q = qs.get("live_offset")
        bridge_offset_q = qs.get("bridge_offset")
        requests_version_q = qs.get("requests_version")
        offset = 0 if offset_q is None else int(offset_q[0])
        live_offset = 0 if live_offset_q is None else int(live_offset_q[0])
        bridge_offset = 0 if bridge_offset_q is None else int(bridge_offset_q[0])
        requests_version = (
            str(requests_version_q[0] or "").strip() or None if requests_version_q else None
        )
        try:
            payload = runtime.api.session_live_payload(
                runtime.MANAGER,
                session_id,
                offset=offset,
                live_offset=live_offset,
                bridge_offset=bridge_offset,
                requests_version=requests_version,
            )
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/workspace"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        try:
            payload = runtime.api.session_workspace_payload(runtime.MANAGER, session_id)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/details"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        try:
            payload = runtime.api.session_details_payload(runtime.MANAGER, session_id)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        runtime.api.json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/diagnostics"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        runtime.MANAGER.refresh_session_meta(session_id, strict=False)
        s = runtime.MANAGER.get_session(session_id)
        if not s:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        try:
            state = runtime.api.validated_session_state(runtime.MANAGER.get_state(session_id))
        except ValueError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        token_val: dict[str, Any] | None = None
        st_token = state.get("token")
        if isinstance(st_token, dict) or st_token is None:
            token_val = st_token if isinstance(st_token, dict) else (s.token if isinstance(s.token, dict) else None)
        model_provider = s.model_provider
        preferred_auth_method = s.preferred_auth_method
        model = s.model
        reasoning_effort = s.reasoning_effort
        service_tier = s.service_tier
        if (
            (model_provider is None or model is None or reasoning_effort is None)
            and s.log_path is not None
            and s.log_path.exists()
        ):
            log_provider, log_model, log_effort = runtime.api.read_run_settings_from_log(
                s.log_path,
                agent_backend=s.agent_backend,
            )
            if model_provider is None:
                model_provider = log_provider
            if model is None:
                model = log_model
            if reasoning_effort is None:
                reasoning_effort = log_effort
        sidebar_meta = runtime.MANAGER.sidebar_meta_get(session_id)
        cwd_path = runtime.api.safe_expanduser(Path(s.cwd))
        if not cwd_path.is_absolute():
            cwd_path = cwd_path.resolve()
        git_branch = runtime.api.current_git_branch(cwd_path)
        updated_ts = runtime.api.display_updated_ts(s)
        elapsed_s = max(0.0, time.time() - updated_ts)
        time_priority = runtime.api.priority_from_elapsed_seconds(elapsed_s)
        base_priority = runtime.api.clip01(time_priority + float(sidebar_meta["priority_offset"]))
        blocked = sidebar_meta["dependency_session_id"] is not None
        snoozed = (
            sidebar_meta["snooze_until"] is not None
            and float(sidebar_meta["snooze_until"]) > time.time()
        )
        final_priority = 0.0 if (snoozed or blocked) else base_priority
        broker_busy = runtime.api.state_busy_value(state)
        busy = runtime.api.display_pi_busy(s, broker_busy=broker_busy) if s.backend == "pi" else broker_busy
        if s.backend != "pi" and s.log_path is not None and s.log_path.exists():
            idle_val = runtime.MANAGER.idle_from_log(session_id)
            busy = broker_busy or (not bool(idle_val))
        runtime.api.json_response(
            handler,
            200,
            {
                "session_id": runtime.api.durable_session_id_for_live_session(s),
                "runtime_id": s.session_id,
                "thread_id": s.thread_id,
                "agent_backend": s.agent_backend,
                "backend": s.backend,
                "owned": bool(s.owned),
                "transport": s.transport,
                "cwd": s.cwd,
                "start_ts": float(s.start_ts),
                "updated_ts": updated_ts,
                "log_path": str(s.log_path) if s.log_path is not None else None,
                "session_file_path": runtime.api.display_source_path(s),
                "broker_pid": int(s.broker_pid),
                "codex_pid": int(s.codex_pid),
                "busy": bool(busy),
                "broker_busy": broker_busy,
                "queue_len": runtime.MANAGER._queue_len(session_id),
                "token": token_val,
                "model_provider": model_provider,
                "preferred_auth_method": preferred_auth_method,
                "provider_choice": runtime.api.provider_choice_for_backend(
                    backend=s.backend,
                    model_provider=model_provider,
                    preferred_auth_method=preferred_auth_method,
                ),
                "model": model,
                "reasoning_effort": reasoning_effort,
                "service_tier": service_tier,
                "tmux_session": s.tmux_session,
                "tmux_window": s.tmux_window,
                "git_branch": git_branch,
                "time_priority": time_priority,
                "base_priority": base_priority,
                "final_priority": final_priority,
                "priority_offset": sidebar_meta["priority_offset"],
                "snooze_until": sidebar_meta["snooze_until"],
                "dependency_session_id": sidebar_meta["dependency_session_id"],
                "todo_snapshot": runtime.api.todo_snapshot_payload_for_session(s),
            },
        )
        return True

    if path.startswith("/api/sessions/") and path.endswith("/queue"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        try:
            q = runtime.MANAGER.queue_list(session_id)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, {"ok": True, "queue": q})
        return True

    if path.startswith("/api/sessions/") and path.endswith("/ui_state"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        try:
            payload = runtime.MANAGER.get_ui_state(session_id)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, payload)
        return True

    session_id = runtime.api.match_session_route(path, "commands")
    if session_id is not None:
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        try:
            payload = runtime.MANAGER.get_session_commands(session_id)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/messages"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        t0_total = time.perf_counter()
        parts = path.split("/")
        if len(parts) < 4:
            handler.send_error(404)
            return True
        session_id = parts[3]
        t0_meta = time.perf_counter()
        runtime.MANAGER.refresh_session_meta(session_id, strict=False)
        dt_meta_ms = (time.perf_counter() - t0_meta) * 1000.0
        s = runtime.MANAGER.get_session(session_id)
        historical_row = runtime.api.historical_session_row(session_id)
        if (not s) and historical_row is None:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        qs = urllib.parse.parse_qs(u.query)
        offset_q = qs.get("offset")
        offset = 0 if offset_q is None else int(offset_q[0])
        if offset < 0:
            offset = 0
        init_q = qs.get("init")
        init = bool(init_q and init_q[0] == "1")
        before_q = qs.get("before")
        before = 0 if before_q is None else int(before_q[0])
        before = max(0, before)
        limit_q = qs.get("limit")
        limit = runtime.SESSION_HISTORY_PAGE_SIZE if limit_q is None else int(limit_q[0])
        limit = max(20, min(runtime.SESSION_HISTORY_PAGE_SIZE, limit))
        payload = runtime.MANAGER.get_messages_page(
            session_id,
            offset=offset,
            init=init,
            limit=limit,
            before=before,
        )
        if isinstance(payload.get("diag"), dict) and s is not None and s.backend != "pi":
            payload["diag"]["meta_refresh_ms"] = round(dt_meta_ms, 3)
        runtime.api.json_response(handler, 200, payload)
        dt_total_ms = (time.perf_counter() - t0_total) * 1000.0
        runtime.api.record_metric("api_messages_init_ms" if init else "api_messages_poll_ms", dt_total_ms)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/tail"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        try:
            tail = runtime.MANAGER.get_tail(session_id)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        runtime.api.json_response(handler, 200, {"tail": tail})
        return True

    if path.startswith("/api/sessions/") and path.endswith("/harness"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        parts = path.split("/")
        if len(parts) < 4:
            handler.send_error(404)
            return True
        session_id = parts[3]
        try:
            cfg = runtime.MANAGER.harness_get(session_id)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        runtime.api.json_response(handler, 200, {"ok": True, **cfg})
        return True

    return False
