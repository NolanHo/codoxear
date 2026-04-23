from __future__ import annotations

from typing import Any

from ...runtime import ServerRuntime
from . import sessions_write_common as _common


def handle_post(runtime: ServerRuntime, handler: Any, path: str) -> bool:
    if path.startswith("/api/sessions/") and path.endswith("/edit"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        obj = _common.read_json_object(runtime, handler)
        name = obj.get("name")
        if not isinstance(name, str):
            runtime.api.json_response(handler, 400, {"error": "name required"})
            return True
        try:
            alias, sidebar_meta = runtime.MANAGER.edit_session(
                session_id,
                name=name,
                priority_offset=obj.get("priority_offset"),
                snooze_until=obj.get("snooze_until"),
                dependency_session_id=obj.get("dependency_session_id"),
            )
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 400, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, {"ok": True, "alias": alias, **sidebar_meta})
        return True

    if path.startswith("/api/sessions/") and path.endswith("/rename"):
        session_id = runtime.api.match_session_route(path, "rename")
        if session_id is None:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _common.read_json_object(runtime, handler)
        name = obj.get("name")
        if not isinstance(name, str):
            runtime.api.json_response(handler, 400, {"error": "name required"})
            return True
        try:
            alias = runtime.MANAGER.alias_set(session_id, name)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        runtime.api.json_response(handler, 200, {"ok": True, "alias": alias})
        return True

    if path.startswith("/api/sessions/") and path.endswith("/focus"):
        session_id = runtime.api.match_session_route(path, "focus")
        if session_id is None:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _common.read_json_object(runtime, handler)
        try:
            focused = runtime.MANAGER.focus_set(session_id, obj.get("focused"))
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 400, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, {"ok": True, "focused": focused})
        return True

    if path.startswith("/api/sessions/") and path.endswith("/send"):
        session_id = runtime.api.match_session_route(path, "send")
        if session_id is None:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _common.read_json_object(runtime, handler)
        text = obj.get("text")
        if not isinstance(text, str) or not text.strip():
            runtime.api.json_response(handler, 400, {"error": "text required"})
            return True
        try:
            res = runtime.MANAGER.send(session_id, text)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, res)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/ui_response"):
        session_id = runtime.api.match_session_route(path, "ui_response")
        if session_id is None:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _common.read_json_object(runtime, handler)
        try:
            runtime.MANAGER.submit_ui_response(session_id, obj)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        durable_session_id = runtime.MANAGER._durable_session_id_for_identifier(session_id) or session_id
        runtime_id = runtime.MANAGER._runtime_session_id_for_identifier(session_id)
        runtime.api.publish_session_workspace_invalidate(
            durable_session_id,
            runtime_id=runtime_id,
            reason="ui_response",
        )
        runtime.api.json_response(handler, 200, {"ok": True})
        return True

    if path.startswith("/api/sessions/") and path.endswith("/enqueue"):
        session_id = runtime.api.match_session_route(path, "enqueue")
        if session_id is None:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _common.read_json_object(runtime, handler)
        text = obj.get("text")
        if not isinstance(text, str) or not text.strip():
            runtime.api.json_response(handler, 400, {"error": "text required"})
            return True
        try:
            res = runtime.MANAGER.enqueue(session_id, text)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, res)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/queue/delete"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        obj = _common.read_json_object(runtime, handler)
        idx = obj.get("index")
        if not isinstance(idx, int):
            runtime.api.json_response(handler, 400, {"error": "index required"})
            return True
        try:
            res = runtime.MANAGER.queue_delete(session_id, idx)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, res)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/queue/update"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        obj = _common.read_json_object(runtime, handler)
        idx = obj.get("index")
        text = obj.get("text")
        if not isinstance(idx, int):
            runtime.api.json_response(handler, 400, {"error": "index required"})
            return True
        if not isinstance(text, str) or not text.strip():
            runtime.api.json_response(handler, 400, {"error": "text required"})
            return True
        try:
            res = runtime.MANAGER.queue_update(session_id, idx, text)
        except KeyError:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, res)
        return True

    return False
