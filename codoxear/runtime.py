from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Any


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
    )
