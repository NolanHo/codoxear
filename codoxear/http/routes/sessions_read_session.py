from __future__ import annotations

import time
import urllib.parse
from typing import Any

from ...runtime import ServerRuntime
from . import route_common as _route
from . import sessions_read_common as _common


def _matches_session_endpoint(path: str, suffix: str) -> bool:
    return path.startswith("/api/sessions/") and path.endswith(suffix)


def _require_prefixed_session_id(path: str, handler: Any) -> str | None:
    session_id = _common.session_id_from_path(path)
    if session_id:
        return session_id
    handler.send_error(404)
    return None


def _path_part_session_id(path: str, handler: Any) -> str | None:
    parts = path.split("/")
    if len(parts) < 4:
        handler.send_error(404)
        return None
    return parts[3]


def _handle_live(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
    u: Any,
) -> bool:
    if not _matches_session_endpoint(ctx.path, "/live"):
        return False
    if not guard.require_auth():
        return True
    session_id = _require_prefixed_session_id(ctx.path, ctx.handler)
    if session_id is None:
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
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_live_payload(
            session_id,
            offset=offset,
            live_offset=live_offset,
            bridge_offset=bridge_offset,
            requests_version=requests_version,
        )
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    return responder.ok(payload)


def _handle_workspace(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
    _u: Any,
) -> bool:
    if not _matches_session_endpoint(ctx.path, "/workspace"):
        return False
    if not guard.require_auth():
        return True
    session_id = _require_prefixed_session_id(ctx.path, ctx.handler)
    if session_id is None:
        return True
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_workspace_payload(session_id)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    return responder.ok(payload)


def _handle_details(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
    _u: Any,
) -> bool:
    if not _matches_session_endpoint(ctx.path, "/details"):
        return False
    if not guard.require_auth():
        return True
    session_id = _require_prefixed_session_id(ctx.path, ctx.handler)
    if session_id is None:
        return True
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_details_payload(session_id)
    except KeyError:
        return responder.not_found()
    return responder.ok(payload)


def _handle_diagnostics(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
    _u: Any,
) -> bool:
    if not _matches_session_endpoint(ctx.path, "/diagnostics"):
        return False
    if not guard.require_auth():
        return True
    session_id = _require_prefixed_session_id(ctx.path, ctx.handler)
    if session_id is None:
        return True

    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_diagnostics_payload(session_id)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    return responder.ok(payload)


def _handle_queue(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
    _u: Any,
) -> bool:
    if not _matches_session_endpoint(ctx.path, "/queue"):
        return False
    if not guard.require_auth():
        return True
    session_id = _require_prefixed_session_id(ctx.path, ctx.handler)
    if session_id is None:
        return True
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_queue_payload(session_id)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    return responder.ok(payload)


def _handle_ui_state(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
    _u: Any,
) -> bool:
    if not _matches_session_endpoint(ctx.path, "/ui_state"):
        return False
    if not guard.require_auth():
        return True
    session_id = _require_prefixed_session_id(ctx.path, ctx.handler)
    if session_id is None:
        return True
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_ui_state_payload(session_id)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    return responder.ok(payload)


def _handle_commands(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
    _u: Any,
) -> bool:
    session_id = guard.session_id("commands")
    if session_id is None:
        return False
    if not guard.require_auth():
        return True
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_commands_payload(session_id)
    except KeyError:
        return responder.not_found()
    except ValueError as exc:
        return responder.upstream_error(str(exc))
    return responder.ok(payload)


def _handle_messages(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
    u: Any,
) -> bool:
    if not _matches_session_endpoint(ctx.path, "/messages"):
        return False
    if not guard.require_auth():
        return True

    t0_total = time.perf_counter()
    session_id = _path_part_session_id(ctx.path, ctx.handler)
    if session_id is None:
        return True

    assert ctx.facade is not None

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
    limit = ctx.runtime.api.SESSION_HISTORY_PAGE_SIZE if limit_q is None else int(limit_q[0])
    limit = max(20, min(ctx.runtime.api.SESSION_HISTORY_PAGE_SIZE, limit))

    try:
        payload = ctx.facade.session_messages_payload(
            session_id,
            offset=offset,
            init=init,
            limit=limit,
            before=before,
        )
    except KeyError:
        return responder.not_found()

    responder.ok(payload)
    dt_total_ms = (time.perf_counter() - t0_total) * 1000.0
    ctx.runtime.api.record_metric(
        "api_messages_init_ms" if init else "api_messages_poll_ms",
        dt_total_ms,
    )
    return True


def _handle_tail(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
    _u: Any,
) -> bool:
    if not _matches_session_endpoint(ctx.path, "/tail"):
        return False
    if not guard.require_auth():
        return True
    session_id = _common.session_id_from_path(ctx.path)
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_tail_payload(session_id)
    except KeyError:
        return responder.not_found()
    return responder.ok(payload)


def _handle_harness(
    ctx: _route.RouteContext,
    guard: _route.SessionRouteGuard,
    responder: _route.RouteResponder,
    _u: Any,
) -> bool:
    if not _matches_session_endpoint(ctx.path, "/harness"):
        return False
    if not guard.require_auth():
        return True
    session_id = _path_part_session_id(ctx.path, ctx.handler)
    if session_id is None:
        return True
    assert ctx.facade is not None
    try:
        payload = ctx.facade.session_harness_payload(session_id)
    except KeyError:
        return responder.not_found()
    return responder.ok(payload)


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    ctx = _route.RouteContext(runtime=runtime, handler=handler, path=path)
    responder = _route.RouteResponder(ctx)
    guard = _route.SessionRouteGuard(ctx, responder)
    for endpoint in (
        _handle_live,
        _handle_workspace,
        _handle_details,
        _handle_diagnostics,
        _handle_queue,
        _handle_ui_state,
        _handle_commands,
        _handle_messages,
        _handle_tail,
        _handle_harness,
    ):
        if endpoint(ctx, guard, responder, u):
            return True
    return False
