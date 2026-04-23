from __future__ import annotations

from typing import Any

from ...runtime import ServerRuntime
from . import sessions_write_actions as _actions
from . import sessions_write_create as _create
from . import sessions_write_harness as _harness


def handle_post(runtime: ServerRuntime, handler: Any, path: str, _u: Any) -> bool:
    for module in (_create, _actions, _harness):
        if module.handle_post(runtime, handler, path):
            return True
    return False
