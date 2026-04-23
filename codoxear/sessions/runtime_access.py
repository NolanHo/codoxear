from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from ..runtime import ServerRuntime, build_server_runtime


def manager_runtime(manager: Any) -> ServerRuntime:
    runtime = getattr(manager, "_runtime", None)
    if isinstance(runtime, ServerRuntime):
        return runtime

    module_name = getattr(getattr(manager, "__class__", None), "__module__", "")
    module = sys.modules.get(module_name)
    if not isinstance(module, ModuleType):
        raise RuntimeError("manager runtime is not initialized")

    event_hub = getattr(module, "EVENT_HUB", None)
    if event_hub is None:
        raise RuntimeError("manager runtime event hub is not initialized")

    api_factory = getattr(module, "_build_runtime_api", None)
    api = api_factory() if callable(api_factory) else None
    runtime = build_server_runtime(module, manager=manager, event_hub=event_hub, api=api)
    manager._runtime = runtime
    return runtime
