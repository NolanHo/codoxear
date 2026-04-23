from __future__ import annotations

from .manager_delegates_lifecycle import SessionManagerLifecycleDelegates
from .manager_delegates_runtime import SessionManagerRuntimeDelegates
from .manager_delegates_state import SessionManagerStateDelegates


class SessionManagerDelegates(
    SessionManagerLifecycleDelegates,
    SessionManagerStateDelegates,
    SessionManagerRuntimeDelegates,
):
    pass
