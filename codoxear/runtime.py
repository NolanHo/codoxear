from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Any


@dataclass(slots=True)
class ServerRuntime:
    module: ModuleType
    manager: Any
    event_hub: Any

    def __getattr__(self, name: str) -> Any:
        return getattr(self.module, name)


def build_server_runtime(
    module: ModuleType,
    *,
    manager: Any,
    event_hub: Any,
) -> ServerRuntime:
    return ServerRuntime(module=module, manager=manager, event_hub=event_hub)
