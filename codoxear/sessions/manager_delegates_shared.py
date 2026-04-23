from __future__ import annotations

from typing import Any

from .runtime_access import manager_runtime


def _sv(manager: Any):
    return manager_runtime(manager)
