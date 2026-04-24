from __future__ import annotations

from typing import Any

from ...runtime import ServerRuntime
from ...runtime_facade import build_runtime_facade
from . import sessions_write_common as _common


def handle_post(runtime: ServerRuntime, handler: Any, path: str) -> bool:
    facade = build_runtime_facade(runtime)

    if path == "/api/cwd_groups/edit":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        try:
            obj = _common.read_json_object(facade, handler)
            cwd, entry = facade.cwd_group_set(
                cwd=obj.get("cwd"),
                label=obj.get("label"),
                collapsed=obj.get("collapsed"),
            )
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        facade.json_response(handler, 200, {"ok": True, "cwd": cwd, **entry})
        return True

    if path == "/api/sessions":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _common.read_json_object(facade, handler)
        try:
            payload = facade.parse_create_session_request(obj)
        except ValueError as exc:
            err = str(exc)
            out = {"error": err}
            if err == "cwd required":
                out["field"] = "cwd"
            facade.json_response(handler, 400, out)
            return True
        try:
            response_payload = facade.create_session(payload)
        except ValueError as exc:
            out: dict[str, Any] = {"error": str(exc)}
            if str(exc).startswith("cwd "):
                out["field"] = "cwd"
            facade.json_response(handler, 400, out)
            return True
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        facade.json_response(handler, 200, response_payload)
        return True

    session_id = facade.match_session_route(path, "delete")
    if session_id is not None:
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        facade.read_body(handler)
        if not facade.delete_session(session_id):
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        facade.json_response(handler, 200, {"ok": True})
        return True

    session_id = facade.match_session_route(path, "handoff")
    if session_id is not None:
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        facade.read_body(handler)
        try:
            response_payload = facade.handoff_session(session_id)
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        facade.json_response(handler, 200, response_payload)
        return True

    session_id = facade.match_session_route(path, "restart")
    if session_id is not None:
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        facade.read_body(handler)
        try:
            response_payload = facade.restart_session(session_id)
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        facade.json_response(handler, 200, response_payload)
        return True

    return False
