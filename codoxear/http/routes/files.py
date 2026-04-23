from __future__ import annotations

from typing import Any

from ...runtime import ServerRuntime
from . import files_get as _files_get
from . import files_post as _files_post


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    return _files_get.handle_get(runtime, handler, path, u)


def handle_post(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    return _files_post.handle_post(runtime, handler, path, u)
