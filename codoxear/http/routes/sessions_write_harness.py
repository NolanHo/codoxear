from __future__ import annotations

from typing import Any

from ...runtime import ServerRuntime
from ...runtime_facade import build_runtime_facade
from . import sessions_write_common as _common


def handle_post(runtime: ServerRuntime, handler: Any, path: str) -> bool:
    facade = build_runtime_facade(runtime)

    if path.startswith("/api/sessions/") and path.endswith("/harness"):
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        obj = _common.read_json_object(facade, handler)
        enabled_raw = obj.get("enabled", None)
        request_raw = obj.get("request", None)
        cooldown_minutes_raw = obj.get("cooldown_minutes", None)
        remaining_injections_raw = obj.get("remaining_injections", None)
        if "text" in obj:
            facade.json_response(handler, 400, {"error": "unknown field: text (use request)"})
            return True
        enabled = None if enabled_raw is None else bool(enabled_raw)
        if request_raw is not None and not isinstance(request_raw, str):
            facade.json_response(handler, 400, {"error": "request must be a string"})
            return True
        request = request_raw if request_raw is not None else None
        if cooldown_minutes_raw is not None:
            try:
                cooldown_minutes = facade.clean_harness_cooldown_minutes(cooldown_minutes_raw)
            except ValueError as exc:
                facade.json_response(handler, 400, {"error": str(exc)})
                return True
        else:
            cooldown_minutes = None
        if remaining_injections_raw is not None:
            try:
                remaining_injections = facade.clean_harness_remaining_injections(
                    remaining_injections_raw,
                    allow_zero=True,
                )
            except ValueError as exc:
                facade.json_response(handler, 400, {"error": str(exc)})
                return True
        else:
            remaining_injections = None
        try:
            payload = facade.session_harness_set(
                session_id,
                enabled=enabled,
                request=request,
                cooldown_minutes=cooldown_minutes,
                remaining_injections=remaining_injections,
            )
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/interrupt"):
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        facade.read_body(handler)
        try:
            payload = facade.session_interrupt(session_id)
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        except ValueError as exc:
            facade.json_response(handler, 502, {"error": str(exc)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    return False
