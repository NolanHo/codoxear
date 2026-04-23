from __future__ import annotations

import hashlib
import os
import urllib.parse
from pathlib import Path

from ..runtime import ServerRuntime


def file_content_version(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_extension(path: Path) -> str:
    suffix = str(path.suffix or "").lower()
    if not suffix.startswith("."):
        return ""
    return suffix[1:]


def markdown_kind(runtime: ServerRuntime, path: Path) -> str:
    return "markdown" if file_extension(path) in runtime.api.MARKDOWN_EXTENSIONS else "text"


def path_looks_textual(runtime: ServerRuntime, path: Path) -> bool:
    ext = file_extension(path)
    if ext in runtime.api.TEXTUAL_EXTENSIONS:
        return True
    return str(path.name or "").strip().lower() in runtime.api.TEXTUAL_FILENAMES


def looks_like_text_bytes(raw: bytes) -> bool:
    if b"\x00" in raw:
        return False
    for b in raw:
        if b < 32 and b not in (9, 10, 12, 13, 27):
            return False
    return True


def sniff_image_ext(raw: bytes) -> str | None:
    if len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if len(raw) >= 3 and raw[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    return None


def image_content_type(path: Path, raw: bytes) -> str | None:
    if path.suffix.lower() == ".svg":
        return "image/svg+xml; charset=utf-8"
    ext = sniff_image_ext(raw)
    if ext == ".png":
        return "image/png"
    if ext == ".jpg":
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    return None


def pdf_content_type(path: Path, raw: bytes) -> str | None:
    if path.suffix.lower() == ".pdf" or raw.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def file_kind(path: Path, raw: bytes) -> tuple[str, str | None]:
    ctype = image_content_type(path, raw)
    if ctype is not None:
        return "image", ctype
    ctype = pdf_content_type(path, raw)
    if ctype is not None:
        return "pdf", ctype
    return "text", None


def decode_text_view_for_client(
    runtime: ServerRuntime,
    path: Path,
    raw: bytes,
) -> tuple[str, bool, str] | None:
    if b"\x00" in raw:
        return None
    try:
        text = raw.decode("utf-8")
        editable = True
    except UnicodeDecodeError:
        if not path_looks_textual(runtime, path) and not looks_like_text_bytes(raw):
            return None
        text = raw.decode("utf-8", errors="replace")
        editable = False
    return text, editable, file_content_version(raw)


def read_text_file_strict(path: Path, *, max_bytes: int) -> tuple[str, int]:
    st = path.stat()
    size = int(st.st_size)
    if size > max_bytes:
        raise ValueError(f"file too large (max {max_bytes} bytes)")
    data = path.read_bytes()
    if b"\x00" in data:
        raise ValueError("binary file not supported")
    text = data.decode("utf-8", errors="replace")
    return text, size


def read_text_file_for_write(path: Path, *, max_bytes: int) -> tuple[str, int, str]:
    st = path.stat()
    size = int(st.st_size)
    if size > max_bytes:
        raise ValueError(f"file too large (max {max_bytes} bytes)")
    data = path.read_bytes()
    if b"\x00" in data:
        raise ValueError("binary file not supported")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("file is not editable as utf-8 text") from exc
    return text, size, file_content_version(data)


def resolve_unique_bare_filename(search_root: Path, raw_path: str) -> Path | None:
    name = str(raw_path).strip()
    if not name or "/" in name or "\\" in name or "\x00" in name:
        return None
    if "." not in Path(name).name:
        return None
    root = search_root.resolve()
    match: Path | None = None
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d
            not in {
                ".git",
                ".hg",
                ".svn",
                "__pycache__",
                "node_modules",
                "build",
                "dist",
            }
        ]
        if name not in filenames:
            continue
        candidate = (Path(current_root) / name).resolve()
        if match is None:
            match = candidate
            continue
        if candidate != match:
            return None
    return match


def resolve_tracked_file_by_basename(
    runtime: ServerRuntime,
    session_id: str,
    raw_path: str,
) -> Path | None:
    sv = runtime
    name = str(raw_path).strip()
    if not name or "/" in name or "\\" in name or "\x00" in name:
        return None
    try:
        tracked = sv.manager.files_get(session_id)
    except KeyError:
        return None
    match: Path | None = None
    for raw in tracked:
        candidate = sv.api.safe_expanduser(Path(raw)).resolve()
        if candidate.name != name:
            continue
        if match is None:
            match = candidate
            continue
        if candidate != match:
            return None
    return match


def resolve_client_file_path(
    runtime: ServerRuntime,
    *,
    session_id: str,
    raw_path: str,
) -> Path:
    sv = runtime
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("empty path")
    if "\n" in raw_path or len(raw_path) > 1024:
        raise ValueError("invalid path format")

    try:
        path_obj = sv.api.safe_expanduser(Path(raw_path))
        for part in path_obj.parts:
            if len(part.encode("utf-8", errors="ignore")) > 255:
                raise ValueError("invalid path format (name too long)")
    except ValueError:
        raise
    except Exception:
        raise ValueError("invalid path format")

    if not path_obj.is_absolute():
        if session_id:
            sv.manager.refresh_session_meta(session_id, strict=False)
            session = sv.manager.get_session(session_id)
            if session:
                base = sv.api.safe_expanduser(Path(session.cwd))
                if not base.is_absolute():
                    base = base.resolve()
                direct = (base / path_obj).resolve()
                if direct.exists():
                    path_obj = direct
                else:
                    tracked = resolve_tracked_file_by_basename(runtime, session_id, raw_path)
                    if tracked is not None:
                        path_obj = tracked
                        return path_obj
                    try:
                        repo_root = Path(
                            sv.api.run_git(
                                base,
                                ["rev-parse", "--show-toplevel"],
                                timeout_s=sv.api.GIT_DIFF_TIMEOUT_SECONDS,
                                max_bytes=64 * 1024,
                            ).strip()
                        ).resolve()
                    except RuntimeError:
                        repo_root = base.resolve()
                    path_obj = resolve_unique_bare_filename(repo_root, raw_path) or direct
            else:
                path_obj = (Path.cwd() / path_obj).resolve()
        else:
            path_obj = (Path.cwd() / path_obj).resolve()
    else:
        path_obj = path_obj.resolve()
    return path_obj


def read_client_file_view(runtime: ServerRuntime, path_obj: Path):
    sv = runtime
    if not path_obj.exists():
        raise FileNotFoundError("file not found")
    if path_obj.is_dir():
        return sv.api.ClientFileView(kind="directory", size=0)
    if not path_obj.is_file():
        raise ValueError("path is not a file")
    try:
        size = int(path_obj.stat().st_size)
        with path_obj.open("rb") as f:
            prefix = f.read(4096)
    except PermissionError as e:
        raise PermissionError("permission denied") from e
    kind, content_type = file_kind(path_obj, prefix)
    if kind in {"image", "pdf"}:
        return sv.api.ClientFileView(kind=kind, size=size, content_type=content_type)
    if size > sv.api.FILE_READ_MAX_BYTES:
        return sv.api.ClientFileView(
            kind="download_only",
            size=size,
            blocked_reason="too_large",
            viewer_max_bytes=sv.api.FILE_READ_MAX_BYTES,
        )
    raw = path_obj.read_bytes()
    text_payload = decode_text_view_for_client(runtime, path_obj, raw)
    if text_payload is None:
        return sv.api.ClientFileView(kind="download_only", size=size, blocked_reason="binary")
    text, editable, version = text_payload
    return sv.api.ClientFileView(
        kind=markdown_kind(runtime, path_obj),
        size=size,
        text=text,
        editable=editable,
        version=version,
    )


def inspect_openable_file(
    runtime: ServerRuntime,
    path_obj: Path,
) -> tuple[bytes, int, str, str | None]:
    view = read_client_file_view(runtime, path_obj)
    if view.kind == "directory":
        raise ValueError("path is not a file")
    if view.kind == "download_only":
        if view.blocked_reason == "too_large":
            raise ValueError(
                f"file too large (max {runtime.api.FILE_READ_MAX_BYTES} bytes)"
            )
        raise ValueError("binary file not supported")
    raw = path_obj.read_bytes()
    return raw, view.size, view.kind, view.content_type


def inspect_path_metadata(
    runtime: ServerRuntime,
    path_obj: Path,
) -> tuple[int, str, str | None]:
    view = read_client_file_view(runtime, path_obj)
    return view.size, view.kind, view.content_type


def read_text_or_image(
    runtime: ServerRuntime,
    path_obj: Path,
) -> tuple[str, int, str | None, bytes | None]:
    view = read_client_file_view(runtime, path_obj)
    if view.kind in {"image", "pdf", "download_only", "directory"}:
        return view.kind, view.size, view.content_type, None
    raw = path_obj.read_bytes()
    return view.kind, view.size, view.content_type, raw


def read_downloadable_file(path_obj: Path) -> tuple[bytes, int]:
    if not path_obj.exists():
        raise FileNotFoundError("file not found")
    if not path_obj.is_file():
        raise ValueError("path is not a file")
    try:
        raw = path_obj.read_bytes()
    except PermissionError as e:
        raise PermissionError("permission denied") from e
    return raw, len(raw)


def inspect_client_path(
    runtime: ServerRuntime,
    path_obj: Path,
) -> tuple[int, str, str | None]:
    view = read_client_file_view(runtime, path_obj)
    return view.size, view.kind, view.content_type


def download_disposition(path_obj: Path) -> str:
    return f"attachment; filename*=UTF-8''{urllib.parse.quote(path_obj.name, safe='')}"
