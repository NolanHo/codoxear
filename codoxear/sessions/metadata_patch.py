from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import FunctionType
from typing import Any

from ..runtime import ServerRuntime


def _runtime_wrapper(runtime: ServerRuntime, name: str) -> Any | None:
    module = getattr(runtime, "module", None)
    if module is None:
        return None
    wrapper = getattr(module, name, None)
    if not callable(wrapper):
        return None
    if (
        isinstance(wrapper, FunctionType)
        and getattr(wrapper, "__module__", None) == getattr(module, "__name__", None)
        and getattr(wrapper, "__name__", None) == name
    ):
        return None
    return wrapper


@dataclass(slots=True)
class MetadataPatchService:
    runtime: ServerRuntime

    def patch_metadata_session_path(
        self,
        sock: Path,
        session_path: Path,
        *,
        force: bool = False,
    ) -> None:
        wrapper = _runtime_wrapper(self.runtime, "_patch_metadata_session_path")
        if wrapper is not None:
            return wrapper(sock, session_path, force=force)
        patch_metadata_session_path(sock, session_path, force=force)

    def patch_metadata_pi_binding(self, sock: Path, session_path: Path) -> None:
        wrapper = _runtime_wrapper(self.runtime, "_patch_metadata_pi_binding")
        if wrapper is not None:
            return wrapper(sock, session_path)
        patch_metadata_pi_binding(sock, session_path)


def service(runtime: ServerRuntime) -> MetadataPatchService:
    return MetadataPatchService(runtime)


def patch_metadata_session_path(
    sock: Path,
    session_path: Path,
    *,
    force: bool = False,
) -> None:
    meta_path = sock.with_suffix(".json")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            return
        if not force and "session_path" in meta:
            return
        meta["session_path"] = str(session_path)
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    except Exception:
        pass


def patch_metadata_pi_binding(sock: Path, session_path: Path) -> None:
    meta_path = sock.with_suffix(".json")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            return
        changed = False
        if meta.get("backend") != "pi":
            meta["backend"] = "pi"
            changed = True
        if meta.get("agent_backend") != "pi":
            meta["agent_backend"] = "pi"
            changed = True
        if meta.get("session_path") != str(session_path):
            meta["session_path"] = str(session_path)
            changed = True
        if not changed:
            return
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    except Exception:
        pass
