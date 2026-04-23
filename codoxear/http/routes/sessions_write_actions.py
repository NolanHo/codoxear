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
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_edit(session_id, obj)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.bad_request(str(exc))
    return responder.ok(payload)


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
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_rename(session_id, name=name)
    except KeyError:
        return responder.not_found()
    return responder.ok(payload)


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
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_focus(session_id, focused=obj.get("focused"))
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.bad_request(str(exc))
    return responder.ok(payload)


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
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_send(session_id, text=text)
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
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_submit_ui_response(session_id, obj)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    return responder.ok(payload)


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
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_enqueue(session_id, text=text)
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
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_queue_delete(session_id, index=idx)
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
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_queue_update(session_id, index=idx, text=text)
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
