from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Any

_GET_ROUTE_MODULE_ATTRS = (
    "_http_assets_routes",
    "_http_auth_routes",
    "_http_events_routes",
    "_http_notification_routes",
    "_http_session_read_routes",
    "_http_file_routes",
)

_POST_ROUTE_MODULE_ATTRS = (
    "_http_auth_routes",
    "_http_notification_routes",
    "_http_session_write_routes",
    "_http_file_routes",
)


def _module_attr(module: ModuleType, name: str) -> Any:
    if hasattr(module, name):
        return getattr(module, name)
    public_name = name[1:] if name.startswith("_") else name
    if hasattr(module, public_name):
        return getattr(module, public_name)
    raise AttributeError(name)


def _route_modules(
    module: ModuleType,
    names: tuple[str, ...],
    *,
    required: bool,
) -> tuple[Any, ...]:
    route_modules: list[Any] = []
    for name in names:
        try:
            route_modules.append(_module_attr(module, name))
        except AttributeError:
            if required:
                raise
    return tuple(route_modules)


class RuntimeApi:
    __slots__ = ("_module", "_exports")

    def __init__(self, module: ModuleType, *, exports: tuple[str, ...]) -> None:
        self._module = module
        self._exports = frozenset(exports)

    def __getattr__(self, name: str) -> Any:
        if name not in self._exports:
            raise AttributeError(name)
        if hasattr(self._module, name):
            return getattr(self._module, name)
        prefixed = f"_{name}"
        if hasattr(self._module, prefixed):
            return getattr(self._module, prefixed)
        raise AttributeError(name)


@dataclass(slots=True)
class ServerRuntime:
    module: ModuleType
    _manager: Any
    event_hub: Any
    api: RuntimeApi | None = None
    get_route_modules: tuple[Any, ...] = ()
    post_route_modules: tuple[Any, ...] = ()

    @property
    def manager(self) -> Any:
        return getattr(self.module, "MANAGER", self._manager)

    @manager.setter
    def manager(self, value: Any) -> None:
        self._manager = value


def build_server_runtime(
    module: ModuleType,
    *,
    manager: Any,
    event_hub: Any,
    api: RuntimeApi | None = None,
    require_route_modules: bool = False,
) -> ServerRuntime:
    resolved_api = api
    if resolved_api is None:
        api_factory = getattr(module, "_build_runtime_api", None)
        if callable(api_factory):
            resolved_api = api_factory()
    return ServerRuntime(
        module=module,
        _manager=manager,
        event_hub=event_hub,
        api=resolved_api,
        get_route_modules=_route_modules(
            module, _GET_ROUTE_MODULE_ATTRS, required=require_route_modules
        ),
        post_route_modules=_route_modules(
            module, _POST_ROUTE_MODULE_ATTRS, required=require_route_modules
        ),
    )
