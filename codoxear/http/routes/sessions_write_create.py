from __future__ import annotations

from typing import Any

from ...runtime import ServerRuntime
from ...sessions import creation as _session_creation
from . import sessions_write_common as _common


def handle_post(runtime: ServerRuntime, handler: Any, path: str) -> bool:
    if path == "/api/cwd_groups/edit":
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        try:
            obj = _common.read_json_object(runtime, handler)
            cwd, entry = runtime.manager.cwd_group_set(
                cwd=obj.get("cwd"),
                label=obj.get("label"),
                collapsed=obj.get("collapsed"),
            )
        except ValueError as exc:
            runtime.api.json_response(handler, 400, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, {"ok": True, "cwd": cwd, **entry})
        return True

    if path == "/api/sessions":
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _common.read_json_object(runtime, handler)
        try:
            payload = _session_creation.parse_create_session_request(runtime, obj)
        except ValueError as exc:
            err = str(exc)
            out = {"error": err}
            if err == "cwd required":
                out["field"] = "cwd"
            runtime.api.json_response(handler, 400, out)
            return True
        try:
            res = runtime.manager.spawn_web_session(
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
            alias = runtime.manager.set_created_session_name(
                session_id=res.get("session_id"),
                runtime_id=res.get("runtime_id"),
                backend=res.get("backend") or payload["backend"],
                name=payload["name"],
            )
        except ValueError as exc:
            response_payload: dict[str, Any] = {"error": str(exc)}
            if str(exc).startswith("cwd "):
                response_payload["field"] = "cwd"
            runtime.api.json_response(handler, 400, response_payload)
            return True
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        response_payload = {"ok": True, **res}
        if alias:
            response_payload["alias"] = alias
        runtime.api.publish_sessions_invalidate(reason="session_created")
        runtime.api.json_response(handler, 200, response_payload)
        return True

    session_id = runtime.api.match_session_route(path, "delete")
    if session_id is not None:
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        runtime.api.read_body(handler)
        ok = runtime.manager.delete_session(session_id)
        if not ok:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        runtime.api.publish_sessions_invalidate(reason="session_deleted")
        runtime.api.json_response(handler, 200, {"ok": True})
        return True

    session_id = runtime.api.match_session_route(path, "handoff")
    if session_id is not None:
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        runtime.api.read_body(handler)
        try:
            res = runtime.manager.handoff_session(session_id)
        except ValueError as exc:
            runtime.api.json_response(handler, 400, {"error": str(exc)})
            return True
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        runtime.api.publish_sessions_invalidate(reason="session_created")
        runtime.api.json_response(handler, 200, {"ok": True, **res})
        return True

    session_id = runtime.api.match_session_route(path, "restart")
    if session_id is not None:
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        runtime.api.read_body(handler)
        try:
            res = runtime.manager.restart_session(session_id)
        except ValueError as exc:
            runtime.api.json_response(handler, 400, {"error": str(exc)})
            return True
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        runtime.api.publish_sessions_invalidate(reason="session_created")
        runtime.api.json_response(handler, 200, {"ok": True, **res})
        return True

    return False
