from __future__ import annotations

import base64
import urllib.parse
from pathlib import Path
from typing import Any

from ..runtime import ServerRuntime


def _session_base(runtime: ServerRuntime, session_id: str, *, strict: bool = False) -> tuple[Any, Path]:
    runtime.MANAGER.refresh_session_meta(session_id, strict=strict)
    session = runtime.MANAGER.get_session(session_id)
    if session is None:
        raise KeyError("unknown session")
    base = runtime._safe_expanduser(Path(session.cwd))
    if not base.is_absolute():
        base = base.resolve()
    return session, base


def _track_file(runtime: ServerRuntime, session_id: str, path_obj: Path) -> None:
    try:
        runtime.MANAGER.files_add(session_id, str(path_obj))
    except KeyError:
        pass


def read_session_file(runtime: ServerRuntime, session_id: str, rel: str) -> dict[str, Any]:
    _session, base = _session_base(runtime, session_id, strict=False)
    path_obj = runtime._resolve_session_path(base, rel)
    if not path_obj.exists():
        raise FileNotFoundError("file not found")
    if not path_obj.is_file():
        raise ValueError("path is not a file")
    view = runtime._read_client_file_view(path_obj)
    _track_file(runtime, session_id, path_obj)
    if view.kind == "image":
        return {
            "ok": True,
            "kind": "image",
            "content_type": view.content_type,
            "path": str(path_obj),
            "rel": str(rel),
            "size": int(view.size),
            "image_url": f"/api/sessions/{session_id}/file/blob?path={urllib.parse.quote(rel)}",
        }
    if view.kind == "pdf":
        return {
            "ok": True,
            "kind": "pdf",
            "content_type": view.content_type,
            "path": str(path_obj),
            "rel": str(rel),
            "size": int(view.size),
            "pdf_url": f"/api/sessions/{session_id}/file/blob?path={urllib.parse.quote(rel)}",
        }
    if view.kind == "download_only":
        return {
            "ok": True,
            "kind": "download_only",
            "path": str(path_obj),
            "rel": str(rel),
            "size": int(view.size),
            "reason": view.blocked_reason,
            "viewer_max_bytes": view.viewer_max_bytes,
        }
    return {
        "ok": True,
        "kind": view.kind,
        "path": str(path_obj),
        "rel": str(rel),
        "size": int(view.size),
        "text": view.text,
        "editable": bool(view.editable),
        "version": view.version,
    }


def search_session_files(runtime: ServerRuntime, session_id: str, query: str, limit: int) -> dict[str, Any]:
    _session, base = _session_base(runtime, session_id, strict=False)
    result = runtime._search_session_relative_files(base, query=query, limit=limit)
    return {
        "ok": True,
        "cwd": str(base),
        "query": result["query"],
        "mode": result["mode"],
        "matches": result["matches"],
        "scanned": result["scanned"],
        "truncated": result["truncated"],
    }


def list_session_files(runtime: ServerRuntime, session_id: str, raw_rel: str) -> dict[str, Any]:
    _session, base = _session_base(runtime, session_id, strict=False)
    entries = runtime._list_session_directory_entries(base, raw_rel)
    return {
        "ok": True,
        "cwd": str(base),
        "path": str(raw_rel or ""),
        "entries": entries,
    }


def resolve_session_blob(runtime: ServerRuntime, session_id: str, rel: str) -> Path:
    _session, base = _session_base(runtime, session_id, strict=False)
    path_obj = runtime._resolve_session_path(base, rel)
    if not path_obj.exists():
        raise FileNotFoundError("file not found")
    if not path_obj.is_file():
        raise ValueError("path is not a file")
    return path_obj


def resolve_client_blob(runtime: ServerRuntime, raw_path: str) -> Path:
    path_obj = runtime._safe_expanduser(Path(raw_path)).resolve()
    if not path_obj.exists():
        raise FileNotFoundError("file not found")
    if not path_obj.is_file():
        raise ValueError("path is not a file")
    return path_obj


def download_session_file(runtime: ServerRuntime, session_id: str, rel: str) -> tuple[Path, bytes, int]:
    path_obj = resolve_session_blob(runtime, session_id, rel)
    raw, size = runtime._read_downloadable_file(path_obj)
    _track_file(runtime, session_id, path_obj)
    return path_obj, raw, size


def read_client_file(runtime: ServerRuntime, path_raw: str, session_id: str = "") -> dict[str, Any]:
    path_obj = runtime._resolve_client_file_path(session_id=session_id, raw_path=path_raw)
    view = runtime._read_client_file_view(path_obj)
    if session_id:
        _track_file(runtime, session_id, path_obj)
    if view.kind == "image":
        return {
            "ok": True,
            "kind": "image",
            "content_type": view.content_type,
            "path": str(path_obj),
            "size": int(view.size),
            "image_url": f"/api/files/blob?path={urllib.parse.quote(str(path_obj))}",
        }
    if view.kind == "pdf":
        return {
            "ok": True,
            "kind": "pdf",
            "content_type": view.content_type,
            "path": str(path_obj),
            "size": int(view.size),
            "pdf_url": f"/api/files/blob?path={urllib.parse.quote(str(path_obj))}",
        }
    if view.kind == "download_only":
        return {
            "ok": True,
            "kind": "download_only",
            "path": str(path_obj),
            "size": int(view.size),
            "reason": view.blocked_reason,
            "viewer_max_bytes": view.viewer_max_bytes,
        }
    return {
        "ok": True,
        "kind": view.kind,
        "path": str(path_obj),
        "size": int(view.size),
        "text": view.text,
        "editable": bool(view.editable),
        "version": view.version,
    }


def inspect_client_file(runtime: ServerRuntime, path_raw: str, session_id: str = "") -> dict[str, Any]:
    path_obj = runtime._resolve_client_file_path(session_id=session_id, raw_path=path_raw)
    view = runtime._read_client_file_view(path_obj)
    return {
        "ok": True,
        "path": str(path_obj),
        "kind": view.kind,
        "content_type": view.content_type,
        "size": int(view.size),
        "reason": view.blocked_reason,
        "viewer_max_bytes": view.viewer_max_bytes,
    }


def write_session_file(
    runtime: ServerRuntime,
    session_id: str,
    *,
    path_raw: str,
    text: str,
    create: bool,
    version: str | None,
) -> dict[str, Any]:
    session, base = _session_base(runtime, session_id, strict=True)
    if create:
        path_obj = runtime._resolve_under(base, path_raw)
        try:
            size, next_version = runtime._write_new_text_file_atomic(path_obj, text=text)
        except FileExistsError as exc:
            raise FileExistsError(str(path_obj)) from exc
    else:
        path_obj = runtime._resolve_session_path(base, path_raw)
        _current_text, _current_size, current_version = runtime._read_text_file_for_write(
            path_obj, max_bytes=runtime.FILE_READ_MAX_BYTES
        )
        if current_version != version:
            raise FileExistsError(str(path_obj), current_version)
        size, next_version = runtime._write_text_file_atomic(path_obj, text=text)
    _track_file(runtime, session_id, path_obj)
    return {
        "ok": True,
        "path": str(path_obj),
        "rel": str(path_raw),
        "size": int(size),
        "version": next_version,
        "editable": True,
        "backend": getattr(session, "backend", None),
    }


def inject_session_attachment(
    runtime: ServerRuntime,
    session_id: str,
    *,
    filename: str,
    attachment_index: int,
    data_b64: str,
) -> dict[str, Any]:
    session, _base = _session_base(runtime, session_id, strict=False)
    if session.backend == "pi":
        raise RuntimeError("pi-attachment-injection")
    try:
        raw = base64.b64decode(data_b64.encode("ascii"), validate=True)
    except Exception as exc:
        raise ValueError("invalid base64") from exc
    out_path = runtime._stage_uploaded_file(session_id, filename, raw)
    inject_text = runtime._attachment_inject_text(attachment_index, out_path)
    seq = f"\x1b[200~{inject_text}\x1b[201~"
    try:
        broker = runtime.MANAGER.inject_keys(session_id, seq)
    except ValueError as exc:
        raise ConnectionError(str(exc)) from exc
    return {
        "ok": True,
        "path": str(out_path),
        "inject_text": inject_text,
        "broker": broker,
    }
