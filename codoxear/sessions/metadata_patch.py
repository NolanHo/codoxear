from __future__ import annotations

import json
from pathlib import Path


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
