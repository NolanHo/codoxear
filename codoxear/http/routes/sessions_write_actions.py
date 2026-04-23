from __future__ import annotations

from typing import Any

from ...runtime import ServerRuntime
from . import route_common as _route
from . import sessions_write_common as _common


def _require_name(obj: dict[str, Any], responder: _route.RouteResponder) -> str | None:
    name = obj.get("name")
    if isinstance(name, str):
        return name
    responder.bad_request("name required")
    return None


def _require_text(obj: dict[str, Any], responder: _route.RouteResponder) -> str | None:
    text = obj.get("text")
    if isinstance(text, str) and text.strip():
        return text
    responder.bad_request("text required")
    return None


def _handle_edit(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
) -> bool:
    if not (ctx.path.startswith("/api/sessions/") and ctx.path.endswith("/edit")):
        return False
    if not guard.require_auth():
        return True
    session_id = _common.session_id_from_path(ctx.path)
    obj = _common.read_json_object(ctx.runtime, ctx.handler)
    name = _require_name(obj, responder)
    if name is None:
        return True
    try:
        alias, sidebar_meta = ctx.runtime.manager.edit_session(
            session_id,
            name=name,
            priority_offset=obj.get("priority_offset"),
            snooze_until=obj.get("snooze_until"),
            dependency_session_id=obj.get("dependency_session_id"),
        )
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.bad_request(str(exc))
    return responder.ok({"ok": True, "alias": alias, **sidebar_meta})


def _handle_rename(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
) -> bool:
    if not (ctx.path.startswith("/api/sessions/") and ctx.path.endswith("/rename")):
        return False
    session_id = guard.session_id("rename")
    if session_id is None:
        return responder.not_found()
    if not guard.require_auth():
        return True
    obj = _common.read_json_object(ctx.runtime, ctx.handler)
    name = _require_name(obj, responder)
    if name is None:
        return True
    try:
        alias = ctx.runtime.manager.alias_set(session_id, name)
    except KeyError:
        return responder.not_found()
    return responder.ok({"ok": True, "alias": alias})


def _handle_focus(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
) -> bool:
    if not (ctx.path.startswith("/api/sessions/") and ctx.path.endswith("/focus")):
        return False
    session_id = guard.session_id("focus")
    if session_id is None:
        return responder.not_found()
    if not guard.require_auth():
        return True
    obj = _common.read_json_object(ctx.runtime, ctx.handler)
    try:
        focused = ctx.runtime.manager.focus_set(session_id, obj.get("focused"))
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.bad_request(str(exc))
    return responder.ok({"ok": True, "focused": focused})


def _handle_send(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
) -> bool:
    if not (ctx.path.startswith("/api/sessions/") and ctx.path.endswith("/send")):
        return False
    session_id = guard.session_id("send")
    if session_id is None:
        return responder.not_found()
    if not guard.require_auth():
        return True
    obj = _common.read_json_object(ctx.runtime, ctx.handler)
    text = _require_text(obj, responder)
    if text is None:
        return True
    try:
        payload = ctx.runtime.manager.send(session_id, text)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    return responder.ok(payload)


def _handle_ui_response(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
) -> bool:
    if not (ctx.path.startswith("/api/sessions/") and ctx.path.endswith("/ui_response")):
        return False
    session_id = guard.session_id("ui_response")
    if session_id is None:
        return responder.not_found()
    if not guard.require_auth():
        return True
    obj = _common.read_json_object(ctx.runtime, ctx.handler)
    try:
        ctx.runtime.manager.submit_ui_response(session_id, obj)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    durable_session_id = ctx.runtime.manager._durable_session_id_for_identifier(session_id) or session_id
    runtime_id = ctx.runtime.manager._runtime_session_id_for_identifier(session_id)
    ctx.runtime.api.publish_session_workspace_invalidate(
        durable_session_id,
        runtime_id=runtime_id,
        reason="ui_response",
    )
    return responder.ok({"ok": True})


def _handle_enqueue(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
) -> bool:
    if not (ctx.path.startswith("/api/sessions/") and ctx.path.endswith("/enqueue")):
        return False
    session_id = guard.session_id("enqueue")
    if session_id is None:
        return responder.not_found()
    if not guard.require_auth():
        return True
    obj = _common.read_json_object(ctx.runtime, ctx.handler)
    text = _require_text(obj, responder)
    if text is None:
        return True
    try:
        payload = ctx.runtime.manager.enqueue(session_id, text)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    return responder.ok(payload)


def _handle_queue_delete(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
) -> bool:
    if not (ctx.path.startswith("/api/sessions/") and ctx.path.endswith("/queue/delete")):
        return False
    if not guard.require_auth():
        return True
    session_id = _common.session_id_from_path(ctx.path)
    obj = _common.read_json_object(ctx.runtime, ctx.handler)
    idx = obj.get("index")
    if not isinstance(idx, int):
        return responder.bad_request("index required")
    try:
        payload = ctx.runtime.manager.queue_delete(session_id, idx)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    return responder.ok(payload)


def _handle_queue_update(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
) -> bool:
    if not (ctx.path.startswith("/api/sessions/") and ctx.path.endswith("/queue/update")):
        return False
    if not guard.require_auth():
        return True
    session_id = _common.session_id_from_path(ctx.path)
    obj = _common.read_json_object(ctx.runtime, ctx.handler)
    idx = obj.get("index")
    if not isinstance(idx, int):
        return responder.bad_request("index required")
    text = _require_text(obj, responder)
    if text is None:
        return True
    try:
        payload = ctx.runtime.manager.queue_update(session_id, idx, text)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    return responder.ok(payload)


def handle_post(runtime: ServerRuntime, handler: Any, path: str) -> bool:
    ctx = _route.RouteContext(runtime=runtime, handler=handler, path=path)
    responder = _route.RouteResponder(ctx)
    guard = _route.SessionRouteGuard(ctx, responder)
    for endpoint in (
        _handle_edit,
        _handle_rename,
        _handle_focus,
        _handle_send,
        _handle_ui_response,
        _handle_enqueue,
        _handle_queue_delete,
        _handle_queue_update,
    ):
        if endpoint(ctx, guard, responder):
            return True
    return False
