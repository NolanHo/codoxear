from __future__ import annotations

from typing import Any

from ...runtime import ServerRuntime
from . import sessions_read_bootstrap as _bootstrap
from . import sessions_read_git as _git
from . import sessions_read_session as _session


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    for module in (_bootstrap, _session, _git):
        if module.handle_get(runtime, handler, path, u):
            return True
    return False
