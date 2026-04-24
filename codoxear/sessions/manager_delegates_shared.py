from __future__ import annotations

from typing import Any, Callable

from .runtime_access import manager_runtime


def _sv(manager: Any):
    return manager_runtime(manager)


def _instance_override(
    obj: Any,
    name: str,
    class_func: Callable[..., Any],
) -> Callable[..., Any] | None:
    values = getattr(obj, "__dict__", None)
    if not isinstance(values, dict):
        return None
    override = values.get(name)
    if not callable(override):
        return None
    target = getattr(override, "__func__", override)
    if target is class_func:
        return None
    return override


def _method_override(
    obj: Any,
    name: str,
    class_func: Callable[..., Any],
) -> Callable[..., Any] | None:
    override = getattr(obj, name, None)
    if not callable(override):
        return None
    target = getattr(override, "__func__", override)
    if target is class_func:
        return None
    return override
