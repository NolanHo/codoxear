from __future__ import annotations

import base64
import fnmatch
import os
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


def _resolve_under(base: Path, rel: str) -> Path:
    if not isinstance(rel, str) or not rel.strip():
        raise ValueError("path required")
    if "\x00" in rel:
        raise ValueError("invalid path")
    p = Path(rel)
    if p.is_absolute():
        raise ValueError("path must be relative")
    resolved_base = base.resolve()
    resolved = (resolved_base / p).resolve()
    if (
        not str(resolved).startswith(str(resolved_base) + os.sep)
        and resolved != resolved_base
    ):
        raise ValueError("path escapes session cwd")
    return resolved


def _resolve_session_relative_child(base: Path, raw_path: str) -> Path:
    rel = str(raw_path or "").strip()
    if not rel:
        return base.resolve()
    if "\x00" in rel:
        raise ValueError("invalid path")
    p = Path(rel)
    if p.is_absolute():
        raise ValueError("path must be relative")
    resolved_base = base.resolve()
    resolved = (resolved_base / p).resolve()
    if (
        not str(resolved).startswith(str(resolved_base) + os.sep)
        and resolved != resolved_base
    ):
        raise ValueError("path escapes session cwd")
    return resolved


def _load_root_gitignore_patterns(root: Path) -> list[str]:
    path = root / ".gitignore"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError:
        return []
    patterns: list[str] = []
    for line in raw.splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith("#") or pattern.startswith("!"):
            continue
        patterns.append(pattern)
    return patterns


def _gitignore_matches(rel_path: str, *, is_dir: bool, pattern: str) -> bool:
    candidate = rel_path.strip("/")
    if not candidate:
        return False
    rule = pattern.strip()
    if not rule:
        return False
    dir_only = rule.endswith("/")
    if dir_only and not is_dir:
        return False
    rule = rule.rstrip("/")
    if not rule:
        return False
    anchored = rule.startswith("/")
    rule = rule.lstrip("/")
    if not rule:
        return False

    if "/" in rule:
        return fnmatch.fnmatchcase(candidate, rule)

    parts = candidate.split("/")
    if anchored:
        return fnmatch.fnmatchcase(parts[0], rule)
    return any(fnmatch.fnmatchcase(part, rule) for part in parts)


def _is_ignored_session_relpath(
    rel_path: str, *, is_dir: bool, patterns: list[str]
) -> bool:
    return any(
        _gitignore_matches(rel_path, is_dir=is_dir, pattern=pattern)
        for pattern in patterns
    )


def _session_entry_sort_key(entry: dict[str, str]) -> tuple[int, str]:
    return (0 if entry.get("kind") == "dir" else 1, entry.get("name", ""))


def list_session_directory_entries(
    runtime: ServerRuntime,
    base: Path,
    raw_path: str = "",
) -> list[dict[str, str]]:
    root = runtime._safe_expanduser(base).resolve()
    if not root.exists():
        raise FileNotFoundError("session cwd not found")
    if not root.is_dir():
        raise ValueError("session cwd is not a directory")
    target = _resolve_session_relative_child(root, raw_path)
    if not target.exists():
        raise FileNotFoundError("path not found")
    if not target.is_dir():
        raise ValueError("path is not a directory")

    patterns = _load_root_gitignore_patterns(root)
    out: list[dict[str, str]] = []
    for child in target.iterdir():
        rel = child.relative_to(root).as_posix()
        if child.is_dir() and child.name in runtime.FILE_LIST_IGNORED_DIRS:
            continue
        if _is_ignored_session_relpath(rel, is_dir=child.is_dir(), patterns=patterns):
            continue
        out.append(
            {
                "name": child.name,
                "path": rel,
                "kind": "dir" if child.is_dir() else "file",
            }
        )
    out.sort(key=_session_entry_sort_key)
    return out


def write_text_file_atomic(
    runtime: ServerRuntime,
    path: Path,
    *,
    text: str,
    max_bytes: int | None = None,
) -> tuple[int, str]:
    st = path.stat()
    if not path.is_file():
        raise ValueError("path is not a file")
    if path.is_symlink():
        raise ValueError("symlink write not supported")
    data = text.encode("utf-8")
    size = len(data)
    max_allowed = int(runtime.FILE_READ_MAX_BYTES if max_bytes is None else max_bytes)
    if size > max_allowed:
        raise ValueError(f"file too large (max {max_allowed} bytes)")
    tmp = path.with_name(f".{path.name}.codoxear-tmp-{runtime.secrets.token_hex(6)}")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, st.st_mode & 0o777)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
    return size, runtime._file_content_version(data)


def write_new_text_file_atomic(
    runtime: ServerRuntime,
    path: Path,
    *,
    text: str,
    max_bytes: int | None = None,
) -> tuple[int, str]:
    path = runtime._safe_expanduser(path)
    parent = path.parent
    if not parent.exists():
        raise FileNotFoundError("parent directory not found")
    if not parent.is_dir():
        raise ValueError("parent is not a directory")
    if parent.is_symlink():
        raise ValueError("symlink parent directory not supported")
    if path.exists():
        raise FileExistsError("file already exists")
    data = text.encode("utf-8")
    size = len(data)
    max_allowed = int(runtime.FILE_READ_MAX_BYTES if max_bytes is None else max_bytes)
    if size > max_allowed:
        raise ValueError(f"file too large (max {max_allowed} bytes)")
    tmp = path.with_name(f".{path.name}.codoxear-tmp-{runtime.secrets.token_hex(6)}")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.link(str(tmp), str(path))
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
    return size, runtime._file_content_version(data)


def _safe_filename(name: str, *, default: str = "file") -> str:
    out = []
    base = Path(str(name or "")).name
    for ch in base:
        if ch.isalnum() or ch in ("-", "_", ".", " "):
            out.append(ch)
    s = "".join(out).strip().replace(" ", "_")
    if not s:
        return default
    return s[:96]


def stage_uploaded_file(
    runtime: ServerRuntime,
    session_id: str,
    filename: str,
    raw: bytes,
    *,
    max_bytes: int | None = None,
) -> Path:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id required")
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("filename required")
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("file bytes required")
    data = bytes(raw)
    max_allowed = int(runtime.ATTACH_UPLOAD_MAX_BYTES if max_bytes is None else max_bytes)
    if len(data) > max_allowed:
        raise ValueError(f"file too large (max {max_allowed} bytes)")
    safe_name = _safe_filename(filename, default="file")
    subdir = (runtime.UPLOAD_DIR / session_id).resolve()
    subdir.mkdir(parents=True, exist_ok=True)
    out_path = (subdir / f"{int(runtime._now() * 1000)}_{safe_name}").resolve()
    if not str(out_path).startswith(str(subdir) + os.sep):
        raise ValueError("bad path")
    out_path.write_bytes(data)
    os.chmod(out_path, 0o600)
    return out_path


def attachment_inject_text(attachment_index: int, path: Path) -> str:
    idx = int(attachment_index)
    if idx <= 0:
        raise ValueError("attachment_index must be >= 1")
    return f"Attachment {idx}: {path}\n"


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
    entries = list_session_directory_entries(runtime, base, raw_rel)
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
        path_obj = _resolve_under(base, path_raw)
        try:
            size, next_version = write_new_text_file_atomic(runtime, path_obj, text=text)
        except FileExistsError as exc:
            raise FileExistsError(str(path_obj)) from exc
    else:
        path_obj = runtime._resolve_session_path(base, path_raw)
        _current_text, _current_size, current_version = runtime._read_text_file_for_write(
            path_obj, max_bytes=runtime.FILE_READ_MAX_BYTES
        )
        if current_version != version:
            raise FileExistsError(str(path_obj), current_version)
        size, next_version = write_text_file_atomic(runtime, path_obj, text=text)
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
    out_path = stage_uploaded_file(runtime, session_id, filename, raw)
    inject_text = attachment_inject_text(attachment_index, out_path)
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
