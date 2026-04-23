from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...runtime import ServerRuntime
from ...runtime_facade import RuntimeFacade, build_runtime_facade


@dataclass(slots=True)
class RouteContext:
    runtime: ServerRuntime
    handler: Any
    path: str
    facade: RuntimeFacade | None = None

    def __post_init__(self) -> None:
        if self.facade is None:
            self.facade = build_runtime_facade(self.runtime)


class RouteResponder:
    def __init__(self, ctx: RouteContext) -> None:
        self._ctx = ctx

    def unauthorized(self) -> bool:
        self._ctx.handler._unauthorized()
        return True

    def json(self, status: int, payload: dict[str, Any]) -> bool:
        assert self._ctx.facade is not None
        self._ctx.facade.json_response(self._ctx.handler, status, payload)
        return True

    def ok(self, payload: dict[str, Any]) -> bool:
        return self.json(200, payload)

    def bad_request(self, error: str) -> bool:
        return self.json(400, {"error": error})

    def not_found(self, error: str = "unknown session") -> bool:
        return self.json(404, {"error": error})

    def upstream_error(self, error: str) -> bool:
        return self.json(502, {"error": error})


class SessionRouteGuard:
    def __init__(self, ctx: RouteContext, responder: RouteResponder) -> None:
        self._ctx = ctx
        self._res = responder

    def require_auth(self) -> bool:
        assert self._ctx.facade is not None
        if self._ctx.facade.require_auth(self._ctx.handler):
            return True
        self._ctx.handler._unauthorized()
        return False

    def session_id(self, suffix: str) -> str | None:
        assert self._ctx.facade is not None
        return self._ctx.facade.match_session_route(self._ctx.path, suffix)
