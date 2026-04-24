#!/usr/bin/env python3
from __future__ import annotations

import base64
import copy
import errno
import gzip
import hashlib
import hmac
import http.server
import io
import json
import logging
import math
import os
import re
import secrets
import shlex
import shutil
import signal
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import time
import tomllib
import traceback
import urllib.parse
import uuid
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import pi_messages as _pi_messages
from . import rollout_log as _rollout_log
from .agent_backend import (
    get_agent_backend,
    infer_agent_backend_from_log_path,
    normalize_agent_backend,
)
from .events import publish as _event_publish
from .events.hub import EventHub
from .http import auth_tokens as _http_auth_tokens
from .http import server_runner as _http_server_runner
from .http import static_assets as _http_static_assets
from .http.routes import assets as _http_assets_routes
from .http.routes import auth as _http_auth_routes
from .http.routes import events as _http_events_routes
from .http.routes import files as _http_file_routes
from .http.routes import notifications as _http_notification_routes
from .http.routes import sessions_read as _http_session_read_routes
from .http.routes import sessions_write as _http_session_write_routes
from .page_state_sqlite import (
    DurableSessionRecord,
    PageStateDB,
    SessionRef,
    import_legacy_app_dir_to_db,
)
from .pi import ui_bridge as _pi_ui_bridge
from .pi import ui_payloads as _pi_ui_payloads
from .pi_log import pi_model_context_window as _pi_model_context_window_impl
from .pi_log import pi_user_text as _pi_user_text
from .pi_log import read_pi_run_settings as _read_pi_run_settings
from .pi_log import read_pi_session_id as _read_pi_session_id
from .runtime import RuntimeApi, ServerRuntime, build_server_runtime
from .runtime_api_exports import RUNTIME_API_EXPORTS as _RUNTIME_API_EXPORTS
from .sessions import background as _session_background
from .sessions import lifecycle as _session_lifecycle
from .sessions import listing as _session_listing
from .sessions import live_payloads as _session_live_payloads
from .sessions import manager_delegates as _manager_delegates
from .sessions import message_history as _message_history
from .sessions import metadata_patch as _session_metadata_patch
from .sessions import models as _session_models
from .sessions import page_state as _page_state
from .sessions import payloads as _session_payloads
from .sessions import pi_session_files as _pi_session_files
from .sessions import process_kill as _session_process_kill
from .sessions import resume_candidates as _resume_candidates
from .sessions import session_catalog as _session_catalog
from .sessions import session_settings as _session_settings
from .sessions import spawn_utils as _spawn_utils
from .sessions import session_control as _session_control
from .sessions import session_display as _session_display
from .sessions import sidebar_state as _sidebar_state_module
from .sessions import transport as _session_transport
from .sessions.sidebar_state import SidebarStateFacade
from . import env_file as _env_file
from . import server_constants as _server_constants
from .workspace import file_access as _workspace_file_access
from .workspace import file_search as _workspace_file_search
from .util import find_new_session_log as _find_new_session_log_impl
from .util import (
    find_session_log_for_session_id as _find_session_log_for_session_id_impl,
)
from .util import is_subagent_session_meta as _is_subagent_session_meta
from .util import iter_session_logs as _iter_session_logs_impl
from .util import now as _now
from .util import proc_find_open_rollout_log as _proc_find_open_rollout_log
from .util import read_jsonl_from_offset as _read_jsonl_from_offset_impl
from .util import read_session_meta_payload as _read_session_meta_payload_impl
from .util import subagent_parent_thread_id as _subagent_parent_thread_id
from .voice_push import VoicePushCoordinator

SessionStateKey = SessionRef | str


LOG = logging.getLogger(__name__)
EVENT_HUB = EventHub(max_events=1024)


def _publish_invalidate_event(
    event_type: str,
    *,
    session_id: str | None = None,
    runtime_id: str | None = None,
    reason: str,
    hints: dict[str, Any] | None = None,
    coalesce_ms: int = 300,
) -> dict[str, Any] | None:
    return _event_publish.publish_invalidate_event(
        EVENT_HUB,
        _clean_optional_text,
        event_type,
        session_id=session_id,
        runtime_id=runtime_id,
        reason=reason,
        hints=hints,
        coalesce_ms=coalesce_ms,
    )



def _publish_sessions_invalidate(*, reason: str, coalesce_ms: int = 500) -> dict[str, Any] | None:
    return _event_publish.publish_sessions_invalidate(
        EVENT_HUB,
        _clean_optional_text,
        reason=reason,
        coalesce_ms=coalesce_ms,
    )


def _publish_session_live_invalidate(
    session_id: str,
    *,
    runtime_id: str | None = None,
    reason: str,
    hints: dict[str, Any] | None = None,
    coalesce_ms: int = 300,
) -> dict[str, Any] | None:
    return _event_publish.publish_session_live_invalidate(
        EVENT_HUB,
        _clean_optional_text,
        session_id,
        runtime_id=runtime_id,
        reason=reason,
        hints=hints,
        coalesce_ms=coalesce_ms,
    )



def _publish_session_workspace_invalidate(
    session_id: str,
    *,
    runtime_id: str | None = None,
    reason: str,
    coalesce_ms: int = 300,
) -> dict[str, Any] | None:
    return _event_publish.publish_session_workspace_invalidate(
        EVENT_HUB,
        _clean_optional_text,
        session_id,
        runtime_id=runtime_id,
        reason=reason,
        coalesce_ms=coalesce_ms,
    )



def _publish_session_transport_invalidate(
    session_id: str,
    *,
    runtime_id: str | None = None,
    reason: str,
    coalesce_ms: int = 300,
) -> dict[str, Any] | None:
    return _event_publish.publish_session_transport_invalidate(
        EVENT_HUB,
        _clean_optional_text,
        session_id,
        runtime_id=runtime_id,
        reason=reason,
        coalesce_ms=coalesce_ms,
    )




def _voice_push_publish_callback(event: dict[str, Any]) -> None:
    _publish_invalidate_event(
        str(event.get("type") or "notifications.invalidate"),
        session_id=_clean_optional_text(event.get("session_id")),
        runtime_id=_clean_optional_text(event.get("runtime_id")),
        reason=str(event.get("reason") or "update"),
        hints=event.get("hints") if isinstance(event.get("hints"), dict) else None,
        coalesce_ms=int(event.get("coalesce_ms") or 500),
    )


def _load_env_file(path: Path) -> dict[str, str]:
    return _env_file.load_env_file(path)


for _constant_name in _server_constants.__all__:
    globals()[_constant_name] = getattr(_server_constants, _constant_name)
del _constant_name


def _match_session_route(path: str, *suffix: str) -> str | None:
    parts = path.split("/")
    if len(parts) != 4 + len(suffix):
        return None
    if parts[:3] != ["", "api", "sessions"]:
        return None
    session_id = urllib.parse.unquote(parts[3])
    if not session_id:
        return None
    if tuple(parts[4:]) != tuple(suffix):
        return None
    return session_id


def _strip_url_prefix(prefix: str, path: str) -> str | None:
    if not prefix:
        return path
    if path == prefix:
        return "/"
    if path.startswith(prefix + "/"):
        return path[len(prefix) :]
    return None


def _render_harness_prompt(request: str | None) -> str:
    base = HARNESS_PROMPT_PREFIX.rstrip()
    r = (request or "").strip()
    if not r:
        return base + "\n"
    return base + "\n\n---\n\nAdditional request from user: " + r + "\n"


def _clean_harness_cooldown_minutes(raw: Any) -> int:
    if raw is None:
        return HARNESS_DEFAULT_IDLE_MINUTES
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("harness cooldown_minutes must be an integer")
    if raw < 1:
        raise ValueError("harness cooldown_minutes must be at least 1")
    return int(raw)


def _clean_harness_remaining_injections(raw: Any, *, allow_zero: bool) -> int:
    if raw is None:
        return HARNESS_DEFAULT_MAX_INJECTIONS
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("harness remaining_injections must be an integer")
    minimum = 0 if allow_zero else 1
    if raw < minimum:
        lower = "0" if allow_zero else "1"
        raise ValueError(f"harness remaining_injections must be at least {lower}")
    return int(raw)


_SESSION_ID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I
)
_METRICS_LOCK = threading.Lock()
_METRICS: dict[str, list[float]] = {}


def _record_metric(name: str, value_ms: float) -> None:
    if not isinstance(name, str) or not name:
        return
    v = float(value_ms)
    if not (v >= 0):
        return
    with _METRICS_LOCK:
        arr = _METRICS.get(name)
        if arr is None:
            arr = []
            _METRICS[name] = arr
        arr.append(v)
        if len(arr) > METRICS_WINDOW:
            del arr[: len(arr) - METRICS_WINDOW]


def _metric_percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = max(0.0, min(1.0, float(p))) * float(len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - float(lo)
    return float(sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac)


def _metrics_snapshot() -> dict[str, dict[str, float | int]]:
    out: dict[str, dict[str, float | int]] = {}
    with _METRICS_LOCK:
        items = list(_METRICS.items())
    for name, samples in items:
        if not samples:
            continue
        srt = sorted(float(x) for x in samples)
        out[name] = {
            "count": len(srt),
            "last_ms": float(samples[-1]),
            "p50_ms": _metric_percentile(srt, 0.50),
            "p95_ms": _metric_percentile(srt, 0.95),
            "max_ms": float(srt[-1]),
        }
    return out


def _wait_or_raise(
    proc: subprocess.Popen[bytes], *, label: str, timeout_s: float = 1.5
) -> None:
    return _spawn_utils.service(RUNTIME).wait_or_raise(
        proc,
        label=label,
        timeout_s=timeout_s,
    )


def _drain_stream(f: Any) -> None:
    while True:
        b = f.read(65536)
        if not b:
            break
    f.close()


def _start_proc_stderr_drain(proc: subprocess.Popen[Any]) -> None:
    stderr = getattr(proc, "stderr", None)
    if stderr is None:
        return
    threading.Thread(target=_drain_stream, args=(stderr,), daemon=True).start()


def _tmux_available() -> bool:
    return shutil.which("tmux") is not None


def _ensure_tmux_short_app_dir() -> str:
    return _spawn_utils.service(RUNTIME).ensure_tmux_short_app_dir()


def _wait_for_spawned_broker_meta(
    spawn_nonce: str, *, timeout_s: float = TMUX_META_WAIT_SECONDS
) -> dict[str, Any]:
    return _spawn_utils.service(RUNTIME).wait_for_spawned_broker_meta(
        spawn_nonce,
        timeout_s=timeout_s,
    )


def _spawn_result_from_meta(meta: dict[str, Any]) -> dict[str, Any]:
    return _spawn_utils.service(RUNTIME).spawn_result_from_meta(meta)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # The PID exists but is owned by another user.
        return True


def _descendant_pids(root_pid: int) -> set[int]:
    root = int(root_pid)
    if root <= 0:
        return set()
    children: dict[int, set[int]] = {}
    try:
        entries = PROC_ROOT.iterdir()
    except OSError:
        return set()
    for entry in entries:
        name = entry.name
        if not name.isdigit():
            continue
        pid = int(name)
        stat_path = entry / "stat"
        try:
            stat_text = stat_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        close_idx = stat_text.rfind(")")
        if close_idx < 0:
            continue
        tail = stat_text[close_idx + 2 :].split()
        if len(tail) < 2:
            continue
        try:
            ppid = int(tail[1])
        except ValueError:
            continue
        children.setdefault(ppid, set()).add(pid)

    out: set[int] = set()
    stack = [root]
    while stack:
        cur = stack.pop()
        for child in children.get(cur, set()):
            if child in out:
                continue
            out.add(child)
            stack.append(child)
    return out


def _process_group_alive(root_pid: int) -> bool:
    if root_pid <= 0:
        return False
    try:
        os.killpg(root_pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate_process_group(root_pid: int, *, wait_seconds: float = 1.0) -> bool:
    return _session_process_kill.terminate_process_group(
        RUNTIME,
        root_pid,
        wait_seconds=wait_seconds,
    )


def _terminate_process(pid: int, *, wait_seconds: float = 1.0) -> bool:
    return _session_process_kill.terminate_process(RUNTIME, pid, wait_seconds=wait_seconds)


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _sock_error_definitely_stale(exc: BaseException) -> bool:
    if isinstance(exc, (FileNotFoundError, ConnectionRefusedError, TimeoutError)):
        return True
    if isinstance(exc, OSError):
        return exc.errno in (errno.ENOENT, errno.ECONNREFUSED, errno.ENOTSOCK)
    return False


def _probe_failure_safe_to_prune(*, broker_pid: int, codex_pid: int) -> bool:
    # Probe timeouts can be normal during startup; only prune runtime artifacts
    # once both tracked processes are gone.
    return (not _pid_alive(codex_pid)) and (not _pid_alive(broker_pid))


def _extract_token_update(objs: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _rollout_log._extract_token_update(objs)


def _file_kind(path: Path, raw: bytes) -> tuple[str, str | None]:
    return _workspace_file_access.file_kind(path, raw)


def _json_response(
    handler: http.server.BaseHTTPRequestHandler, status: int, obj: Any
) -> None:
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    accept_encoding = str(handler.headers.get("Accept-Encoding") or "").lower()
    use_gzip = "gzip" in accept_encoding
    if use_gzip:
        body = gzip.compress(body)
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    if use_gzip:
        handler.send_header("Content-Encoding", "gzip")
        handler.send_header("Vary", "Accept-Encoding")
    handler.send_header("Content-Length", str(len(body)))
    try:
        handler.end_headers()
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        # Client disconnected during transmission.
        pass


def _read_body(
    handler: http.server.BaseHTTPRequestHandler, limit: int = 2 * 1024 * 1024
) -> bytes:
    cl = handler.headers.get("Content-Length")
    if cl is None:
        cl = "0"
    cl2 = str(cl).strip()
    if not cl2:
        cl2 = "0"
    n = int(cl2)
    if n < 0 or n > limit:
        raise ValueError(f"invalid content-length: {n}")
    return handler.rfile.read(n)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_or_create_hmac_secret() -> bytes:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if HMAC_SECRET_PATH.exists():
        b = HMAC_SECRET_PATH.read_bytes()
        if len(b) < 32:
            raise ValueError(f"invalid hmac secret (too short): {HMAC_SECRET_PATH}")
        return b[:64]
    secret = os.urandom(64)
    HMAC_SECRET_PATH.write_bytes(secret)
    os.chmod(HMAC_SECRET_PATH, 0o600)
    return secret


HMAC_SECRET = _load_or_create_hmac_secret()


def _require_auth(handler: http.server.BaseHTTPRequestHandler) -> bool:
    return _http_auth_tokens.require_auth(
        handler,
        cookie_name=COOKIE_NAME,
        secret=HMAC_SECRET,
        now_ts=_now(),
    )


def _set_auth_cookie(handler: http.server.BaseHTTPRequestHandler) -> None:
    _http_auth_tokens.set_auth_cookie(
        handler,
        cookie_name=COOKIE_NAME,
        cookie_path=COOKIE_PATH,
        cookie_ttl_seconds=COOKIE_TTL_SECONDS,
        cookie_secure=COOKIE_SECURE,
        secret=HMAC_SECRET,
        now_ts=_now(),
    )


_PASSWORD_CACHE: str | None = None


@dataclass(frozen=True)
class ClientFileView:
    kind: str
    size: int
    content_type: str | None = None
    text: str | None = None
    editable: bool = False
    version: str | None = None
    blocked_reason: str | None = None
    viewer_max_bytes: int | None = None


def _require_password() -> str:
    global _PASSWORD_CACHE
    if _PASSWORD_CACHE is not None:
        return _PASSWORD_CACHE
    pw_raw = os.environ.get("CODEX_WEB_PASSWORD")
    pw = str(pw_raw).strip() if pw_raw is not None else ""
    if not pw:
        raise RuntimeError("CODEX_WEB_PASSWORD is required (set it in .env)")
    _PASSWORD_CACHE = pw
    return pw


def _password_hash() -> str:
    return _sha256_hex(_require_password().encode("utf-8"))


def _is_same_password(pw: str) -> bool:
    return hmac.compare_digest(_sha256_hex(pw.encode("utf-8")), _password_hash())


def _read_text_file_strict(path: Path, *, max_bytes: int) -> tuple[str, int]:
    return _workspace_file_access.read_text_file_strict(path, max_bytes=max_bytes)


def _file_content_version(raw: bytes) -> str:
    return _workspace_file_access.file_content_version(raw)


def _read_text_file_for_write(path: Path, *, max_bytes: int) -> tuple[str, int, str]:
    return _workspace_file_access.read_text_file_for_write(path, max_bytes=max_bytes)


def _safe_expanduser(p: Path) -> Path:
    try:
        return p.expanduser()
    except RuntimeError:
        return p


def _resolve_session_path(base: Path, raw_path: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("path required")
    if "\x00" in raw_path:
        raise ValueError("invalid path")
    p = Path(raw_path)
    if p.is_absolute():
        return _safe_expanduser(p).resolve()
    resolved_base = _safe_expanduser(base)
    if not resolved_base.is_absolute():
        resolved_base = resolved_base.resolve()
    return (resolved_base / p).resolve()


def _resolve_git_path(cwd: Path, raw_path: str) -> tuple[Path, Path, str]:
    repo_root = Path(
        _run_git(
            cwd,
            ["rev-parse", "--show-toplevel"],
            timeout_s=GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=64 * 1024,
        ).strip()
    ).resolve()
    target = _resolve_session_path(cwd, raw_path)
    try:
        rel = str(target.relative_to(repo_root))
    except ValueError as e:
        raise ValueError("path is outside git repo") from e
    return target, repo_root, rel


def _run_git(cwd: Path, args: list[str], *, timeout_s: float, max_bytes: int) -> str:
    cmd = ["git", *args]
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or f"git failed with code {proc.returncode}")
    if len(proc.stdout) > max_bytes:
        raise ValueError(f"git output too large (max {max_bytes} bytes)")
    return proc.stdout.decode("utf-8", errors="replace")


def _expand_user_path(raw: str) -> Path:
    home = str(Path.home())
    expanded = raw.strip().replace("${HOME}", home)
    expanded = re.sub(r"\$HOME(?![A-Za-z0-9_])", home, expanded)
    return Path(os.path.expanduser(os.path.expandvars(expanded)))


def _resolve_dir_target(raw: str, *, field_name: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field_name} required")
    path = _expand_user_path(raw).resolve()
    if path.exists() and not path.is_dir():
        raise ValueError(f"{field_name} is not a directory: {path}")
    return path


def _codex_trust_override_for_path(path: Path) -> str:
    return f'projects={{ {json.dumps(str(path.resolve()))} = {{ trust_level = "trusted" }} }}'


def _clean_worktree_branch(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValueError("worktree_branch must be a string")
    branch = raw.strip()
    if not branch:
        raise ValueError("worktree_branch required")
    return branch


def _require_git_repo(cwd: Path) -> None:
    _run_git(
        cwd,
        ["rev-parse", "--is-inside-work-tree"],
        timeout_s=GIT_DIFF_TIMEOUT_SECONDS,
        max_bytes=4096,
    )


def _git_repo_root(cwd: Path) -> Path | None:
    try:
        root = _run_git(
            cwd,
            ["rev-parse", "--show-toplevel"],
            timeout_s=GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=64 * 1024,
        ).strip()
    except (RuntimeError, FileNotFoundError):
        return None
    if not root:
        return None
    return Path(root).resolve()


def _push_file_search_match(
    heap: list[tuple[int, str]], *, path: str, score: int, limit: int
) -> None:
    return _workspace_file_search._push_file_search_match(
        heap,
        path=path,
        score=score,
        limit=limit,
    )


def _finish_file_search(
    heap: list[tuple[int, str]], *, mode: str, query: str, scanned: int, truncated: bool
) -> dict[str, Any]:
    return _workspace_file_search._finish_file_search(
        heap,
        mode=mode,
        query=query,
        scanned=scanned,
        truncated=truncated,
    )


def _search_session_relative_files(
    base: Path, *, query: str, limit: int = FILE_SEARCH_LIMIT
) -> dict[str, Any]:
    return _workspace_file_search.search_session_relative_files(
        RUNTIME,
        base,
        query=query,
        limit=limit,
    )


def _describe_session_cwd(cwd: Path) -> dict[str, Any]:
    exists = cwd.exists()
    if exists and not cwd.is_dir():
        raise ValueError(f"cwd is not a directory: {cwd}")
    repo_root = _git_repo_root(cwd) if exists else None
    git_branch = (_current_git_branch(cwd) or "") if exists else ""
    return {
        "cwd": str(cwd),
        "exists": exists,
        "will_create": not exists,
        "git_repo": repo_root is not None,
        "git_root": str(repo_root) if repo_root is not None else "",
        "git_branch": git_branch,
    }


def _worktree_path_slug(branch: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip(".-")
    return slug or "worktree"


def _default_worktree_path(source_cwd: Path, branch: str) -> Path:
    slug = _worktree_path_slug(branch)
    return (source_cwd.parent / f"{source_cwd.name}-{slug}").resolve()


def _create_git_worktree(source_cwd: Path, worktree_branch: str) -> Path:
    return _spawn_utils.service(RUNTIME).create_git_worktree(
        source_cwd,
        worktree_branch,
    )


def _parse_git_numstat(text: str) -> dict[str, dict[str, int | None]]:
    return _spawn_utils.service(RUNTIME).parse_git_numstat(text)


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


def _clean_alias(name: str) -> str:
    if not isinstance(name, str):
        return ""
    # Collapse whitespace and cap length to keep titles readable.
    cleaned = " ".join(name.split()).strip()
    if not cleaned:
        return ""
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip()
    return cleaned


def _normalize_cwd_group_key(cwd: Any) -> str:
    if not isinstance(cwd, str) or not cwd.strip():
        raise ValueError("cwd must be a non-empty string")
    trimmed = cwd.strip()
    return str(Path(trimmed).expanduser().resolve(strict=False))


def _existing_workspace_dir(cwd: Any) -> str | None:
    try:
        normalized = _normalize_cwd_group_key(cwd)
    except ValueError:
        return None
    try:
        if not Path(normalized).is_dir():
            return None
    except OSError:
        return None
    return normalized


def _canonical_session_cwd(cwd: Any) -> str | None:
    if not isinstance(cwd, str):
        return None
    trimmed = cwd.strip()
    if not trimmed:
        return None
    try:
        return _normalize_cwd_group_key(trimmed)
    except ValueError:
        return trimmed


def _clean_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _normalize_session_cwd_row(row: dict[str, Any]) -> dict[str, Any]:
    return _session_listing.service(RUNTIME).normalize_session_cwd_row(row)


def _session_list_payload(
    rows: list[dict[str, Any]],
    *,
    group_key: str | None = None,
    offset: int = 0,
    limit: int = SESSION_LIST_PAGE_SIZE,
    group_offset: int = 0,
    group_limit: int = SESSION_LIST_RECENT_GROUP_LIMIT,
) -> dict[str, Any]:
    return _session_listing.service(RUNTIME).session_list_payload(
        rows,
        group_key=group_key,
        offset=offset,
        limit=limit,
        group_offset=group_offset,
        group_limit=group_limit,
    )


def _listed_session_row(manager: "SessionManager", session_id: str) -> dict[str, Any] | None:
    return _session_catalog.service(manager).listed_session_row(session_id)


def _session_details_payload(
    manager: "SessionManager", session_id: str
) -> dict[str, Any]:
    return _session_payloads.service(RUNTIME, manager).session_details_payload(session_id)


def _clean_recent_cwd(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip()
    return out or None


def _clip01(v: float) -> float:
    if v <= 0.0:
        return 0.0
    if v >= 1.0:
        return 1.0
    return float(v)


def _clean_priority_offset(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        raise ValueError("priority_offset must be a number")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError("priority_offset must be finite")
    if out < -1.0 or out > 1.0:
        raise ValueError("priority_offset must be within [-1, 1]")
    return out


def _clean_snooze_until(value: Any) -> float | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, bool):
        raise ValueError("snooze_until must be a unix timestamp or null")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError("snooze_until must be finite")
    if out <= 0:
        return None
    return out


def _clean_dependency_session_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("dependency_session_id must be a string or null")
    out = value.strip()
    return out or None


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip()
    return out or None


def _clean_optional_resume_session_id(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("resume_session_id must be a string")
    out = value.strip()
    return out or None


def _normalize_requested_model(value: Any) -> str | None:
    out = _clean_optional_text(value)
    if out is None:
        return None
    return None if out.lower() == "default" else out


def _display_reasoning_effort(value: Any) -> str | None:
    out = _clean_optional_text(value)
    if out is None:
        return None
    lowered = out.lower()
    return lowered if lowered in SUPPORTED_REASONING_EFFORTS else None


def _display_pi_reasoning_effort(value: Any) -> str | None:
    out = _clean_optional_text(value)
    if out is None:
        return None
    lowered = out.lower()
    return lowered if lowered in SUPPORTED_PI_REASONING_EFFORTS else None


def _normalize_requested_reasoning_effort(value: Any) -> str | None:
    return _session_settings.normalize_requested_reasoning_effort(RUNTIME, value)


def _normalize_requested_pi_reasoning_effort(value: Any) -> str | None:
    return _session_settings.normalize_requested_pi_reasoning_effort(RUNTIME, value)


def _priority_from_elapsed_seconds(elapsed_s: float) -> float:
    if elapsed_s <= 0:
        return 1.0
    return _clip01(math.exp(-SIDEBAR_PRIORITY_LAMBDA * float(elapsed_s)))


def _current_git_branch(cwd: Path) -> str | None:
    try:
        branch = _run_git(
            cwd,
            ["rev-parse", "--abbrev-ref", "HEAD"],
            timeout_s=GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=64 * 1024,
        ).strip()
    except (RuntimeError, FileNotFoundError):
        return None
    if not branch:
        return None
    return branch


def _todo_snapshot_payload_for_session(s: Session) -> dict[str, Any]:
    return _pi_ui_payloads.todo_snapshot_payload_for_session(RUNTIME, s)


def _sanitize_pi_ui_state_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _pi_ui_payloads.sanitize_pi_ui_state_payload(payload)


def _ui_requests_version(requests: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        requests,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).digest()[:12]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _sanitize_pi_commands_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _pi_ui_payloads.sanitize_pi_commands_payload(payload)


def _legacy_pi_ui_response_text(payload: dict[str, Any]) -> str | None:
    return _pi_ui_payloads.legacy_pi_ui_response_text(payload)


def _iter_session_logs(*, agent_backend: str = "codex") -> list[Path]:
    backend_name = normalize_agent_backend(agent_backend)
    sessions_dir = CODEX_SESSIONS_DIR if backend_name == "codex" else PI_SESSIONS_DIR
    return _iter_session_logs_impl(sessions_dir, agent_backend=backend_name)


def _find_session_log_for_session_id(
    session_id: str, *, agent_backend: str = "codex"
) -> Path | None:
    backend_name = normalize_agent_backend(agent_backend)
    sessions_dir = CODEX_SESSIONS_DIR if backend_name == "codex" else PI_SESSIONS_DIR
    return _find_session_log_for_session_id_impl(
        sessions_dir, session_id, agent_backend=backend_name
    )


def _find_new_session_log(
    *,
    agent_backend: str = "codex",
    after_ts: float,
    preexisting: set[Path],
    timeout_s: float = 15.0,
) -> tuple[str, Path] | None:
    backend_name = normalize_agent_backend(agent_backend)
    sessions_dir = CODEX_SESSIONS_DIR if backend_name == "codex" else PI_SESSIONS_DIR
    return _find_new_session_log_impl(
        sessions_dir=sessions_dir,
        agent_backend=backend_name,
        after_ts=after_ts,
        preexisting=preexisting,
        timeout_s=timeout_s,
    )


def _read_jsonl_from_offset(
    path: Path, offset: int, max_bytes: int = 2 * 1024 * 1024
) -> tuple[list[dict[str, Any]], int]:
    return _read_jsonl_from_offset_impl(path, offset, max_bytes=max_bytes)


def _session_id_from_rollout_path(log_path: Path) -> str | None:
    name = log_path.name
    m = _SESSION_ID_RE.findall(name)
    return m[-1] if m else None


def _read_session_meta(
    log_path: Path, *, agent_backend: str | None = None
) -> dict[str, Any]:
    return _session_settings.read_session_meta(
        RUNTIME,
        log_path,
        agent_backend=agent_backend,
    )


def _turn_context_run_settings(payload: Any) -> tuple[str | None, str | None]:
    return _session_settings.turn_context_run_settings(RUNTIME, payload)


def _read_run_settings_from_log(
    log_path: Path, *, agent_backend: str = "codex"
) -> tuple[str | None, str | None, str | None]:
    return _session_settings.read_run_settings_from_log(
        RUNTIME,
        log_path,
        agent_backend=agent_backend,
    )


def _normalize_requested_model_provider(
    value: Any, *, allowed: set[str] | None = None
) -> str | None:
    return _session_settings.normalize_requested_model_provider(
        RUNTIME,
        value,
        allowed=allowed,
    )


def _normalize_requested_service_tier(value: Any) -> str | None:
    return _session_settings.normalize_requested_service_tier(RUNTIME, value)


def _normalize_requested_preferred_auth_method(value: Any) -> str | None:
    return _session_settings.normalize_requested_preferred_auth_method(RUNTIME, value)


def _normalize_requested_backend(raw: Any) -> str:
    return _session_settings.normalize_requested_backend(raw)


def _provider_choice_for_settings(
    *, model_provider: str | None, preferred_auth_method: str | None
) -> str:
    return _session_settings.provider_choice_for_settings(
        model_provider=model_provider,
        preferred_auth_method=preferred_auth_method,
    )


def _provider_choice_for_backend(
    *, backend: str, model_provider: str | None, preferred_auth_method: str | None
) -> str | None:
    return _session_settings.provider_choice_for_backend(
        backend=backend,
        model_provider=model_provider,
        preferred_auth_method=preferred_auth_method,
    )


def _metadata_log_path(
    *, meta: dict[str, Any], backend: str, sock: Path
) -> Path | None:
    return _session_settings.metadata_log_path(meta=meta, backend=backend, sock=sock)


def _metadata_session_path(
    *, meta: dict[str, Any], backend: str, sock: Path
) -> Path | None:
    return _session_settings.metadata_session_path(
        meta=meta,
        backend=backend,
        sock=sock,
    )


def _patch_metadata_session_path(
    sock: Path, session_path: Path, *, force: bool = False
) -> None:
    _session_metadata_patch.patch_metadata_session_path(
        sock,
        session_path,
        force=force,
    )


def _patch_metadata_pi_binding(sock: Path, session_path: Path) -> None:
    _session_metadata_patch.patch_metadata_pi_binding(sock, session_path)


def _resume_candidate_from_log(
    log_path: Path, *, agent_backend: str = "codex"
) -> dict[str, Any] | None:
    return _resume_candidates.service(RUNTIME).resume_candidate_from_log(
        log_path,
        agent_backend=agent_backend,
    )


def _pi_native_session_dir_for_cwd(cwd: str | Path) -> Path:
    return _pi_session_files.service(RUNTIME).pi_native_session_dir_for_cwd(cwd)


def _pi_new_session_file_for_cwd(cwd: str | Path) -> Path:
    return _pi_session_files.service(RUNTIME).pi_new_session_file_for_cwd(cwd)


def _pi_session_has_handoff_history(session_path: Path) -> bool:
    return _pi_session_files.service(RUNTIME).pi_session_has_handoff_history(session_path)


def _next_pi_handoff_history_path(session_path: Path) -> Path:
    return _pi_session_files.service(RUNTIME).next_pi_handoff_history_path(session_path)


def _copy_file_atomic(source_path: Path, target_path: Path) -> None:
    return _pi_session_files.service(RUNTIME).copy_file_atomic(source_path, target_path)


def _pi_session_name_from_session_file(
    session_path: Path, *, max_scan_bytes: int = 512 * 1024
) -> str:
    return _pi_session_files.service(RUNTIME).pi_session_name_from_session_file(
        session_path,
        max_scan_bytes=max_scan_bytes,
    )



def _pi_resume_candidate_from_session_file(session_path: Path) -> dict[str, Any] | None:
    return _resume_candidates.service(RUNTIME).pi_resume_candidate_from_session_file(
        session_path
    )


def _discover_pi_session_for_cwd(
    cwd: str, start_ts: float, *, exclude: set[Path] | None = None
) -> Path | None:
    return _resume_candidates.service(RUNTIME).discover_pi_session_for_cwd(
        cwd,
        start_ts,
        exclude=exclude,
    )


def _resolve_pi_session_path(
    *,
    thread_id: str | None,
    cwd: str,
    start_ts: float,
    preferred: Path | None = None,
    exclude: set[Path] | None = None,
) -> tuple[Path | None, str | None]:
    return _resume_candidates.service(RUNTIME).resolve_pi_session_path(
        thread_id=thread_id,
        cwd=cwd,
        start_ts=start_ts,
        preferred=preferred,
        exclude=exclude,
    )


def _safe_path_mtime(path: Path) -> float | None:
    try:
        return float(path.stat().st_mtime)
    except OSError:
        return None


def _list_resume_candidates_for_cwd(
    cwd: str,
    *,
    limit: int = 12,
    offset: int = 0,
    backend: str | None = None,
    agent_backend: str | None = None,
) -> list[dict[str, Any]]:
    return _resume_candidates.service(RUNTIME).list_resume_candidates_for_cwd(
        cwd,
        limit=limit,
        offset=offset,
        backend=backend,
        agent_backend=agent_backend,
    )


def _iter_all_resume_candidates(*, limit: int = 200) -> list[dict[str, Any]]:
    return _resume_candidates.service(RUNTIME).iter_all_resume_candidates(limit=limit)


def _historical_session_id(backend: str, resume_session_id: str) -> str:
    return _session_listing.service(RUNTIME).historical_session_id(
        backend,
        resume_session_id,
    )


def _parse_historical_session_id(session_id: str) -> tuple[str, str] | None:
    return _session_listing.service(RUNTIME).parse_historical_session_id(session_id)


def _historical_session_row(session_id: str) -> dict[str, Any] | None:
    return _session_listing.historical_session_row(RUNTIME, session_id)


def _historical_sidebar_items(
    *, live_resume_keys: set[tuple[str, str]], now_ts: float
) -> list[dict[str, Any]]:
    return _session_listing.historical_sidebar_items(
        RUNTIME,
        live_resume_keys=live_resume_keys,
        now_ts=now_ts,
    )


def _first_user_message_preview_from_log(
    log_path: Path, *, max_scan_bytes: int = 256 * 1024
) -> str:
    return _session_listing.service(RUNTIME).first_user_message_preview_from_log(
        log_path,
        max_scan_bytes=max_scan_bytes,
    )


def _first_user_message_preview_from_pi_session(
    session_path: Path, *, max_scan_bytes: int = 256 * 1024
) -> str:
    return _session_listing.service(RUNTIME).first_user_message_preview_from_pi_session(
        session_path,
        max_scan_bytes=max_scan_bytes,
    )


def _coerce_main_thread_log(*, thread_id: str, log_path: Path) -> tuple[str, Path]:
    sm = _read_session_meta(log_path)
    if not sm:
        return thread_id, log_path
    if not _is_subagent_session_meta(sm):
        return thread_id, log_path
    parent = _subagent_parent_thread_id(sm)
    if not parent:
        return thread_id, log_path
    parent_log = _find_session_log_for_session_id_impl(CODEX_SESSIONS_DIR, parent)
    if parent_log is None or not parent_log.exists():
        return thread_id, log_path
    return parent, parent_log


def _extract_chat_events(
    objs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, bool], dict[str, Any]]:
    return _rollout_log._extract_chat_events(objs)


def _extract_delivery_messages(objs: list[dict[str, Any]]) -> list[Any]:
    return _rollout_log._extract_delivery_messages(objs)


def _read_jsonl_tail(path: Path, max_bytes: int) -> list[dict[str, Any]]:
    return _rollout_log._read_jsonl_tail(path, max_bytes)


def _read_chat_events_from_tail(
    log_path: Path,
    min_events: int = 120,
    max_scan_bytes: int = 128 * 1024 * 1024,
) -> list[dict[str, Any]]:
    return _rollout_log._read_chat_events_from_tail(
        log_path, min_events=min_events, max_scan_bytes=max_scan_bytes
    )


def _read_chat_tail_snapshot(
    log_path: Path,
    *,
    min_events: int,
    initial_scan_bytes: int,
    max_scan_bytes: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, int, bool, int]:
    return _rollout_log._read_chat_tail_snapshot(
        log_path,
        min_events=min_events,
        initial_scan_bytes=initial_scan_bytes,
        max_scan_bytes=max_scan_bytes,
    )


def _event_ts(obj: dict[str, Any]) -> float | None:
    return _rollout_log._event_ts(obj)


def _has_assistant_output_text(obj: dict[str, Any]) -> bool:
    return _rollout_log._has_assistant_output_text(obj)


def _analyze_log_chunk(
    objs: list[dict[str, Any]],
) -> tuple[int, int, int, float | None, dict[str, Any] | None, list[dict[str, Any]]]:
    return _rollout_log._analyze_log_chunk(objs)


def _last_conversation_ts_from_tail(
    log_path: Path,
    *,
    max_scan_bytes: int | None = None,
) -> float | None:
    return _rollout_log._last_conversation_ts_from_tail(
        log_path, max_scan_bytes=max_scan_bytes
    )


def _compute_idle_from_log(
    path: Path, max_scan_bytes: int = 8 * 1024 * 1024
) -> bool | None:
    return _rollout_log._compute_idle_from_log(path, max_scan_bytes=max_scan_bytes)


def _last_chat_role_ts_from_tail(
    path: Path,
    *,
    max_scan_bytes: int,
) -> tuple[str, float] | None:
    return _rollout_log._last_chat_role_ts_from_tail(
        path, max_scan_bytes=max_scan_bytes
    )


def _session_file_activity_ts(path: Path | None) -> float | None:
    if path is None or not path.exists():
        return None
    try:
        ts = float(path.stat().st_mtime)
    except OSError:
        return None
    if not math.isfinite(ts) or ts <= 0:
        return None
    return ts


def _touch_session_file(path: Path | None) -> float | None:
    """Best-effort touch used to mark local prompt activity for Pi sessions."""
    if path is None:
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
    except OSError:
        return _session_file_activity_ts(path)
    return _session_file_activity_ts(path)


Session = _session_models.Session
BridgeOutboundRequest = _session_models.BridgeOutboundRequest


def _session_supports_live_pi_ui(session: Session) -> bool:
    return _session_display.service(RUNTIME).session_supports_live_pi_ui(session)


def _is_attention_worthy_session_event(event: dict[str, Any]) -> bool:
    return _session_display.service(RUNTIME).is_attention_worthy_session_event(event)



def _attention_updated_ts_from_events(events: list[dict[str, Any]]) -> float | None:
    return _session_display.service(RUNTIME).attention_updated_ts_from_events(events)



def _last_attention_ts_from_pi_tail(
    session_path: Path | None, *, max_scan_bytes: int = 8 * 1024 * 1024
) -> float | None:
    return _session_display.service(RUNTIME).last_attention_ts_from_pi_tail(
        session_path,
        max_scan_bytes=max_scan_bytes,
    )



def _display_updated_ts(s: Session) -> float:
    return _session_display.service(RUNTIME).display_updated_ts(s)


def _session_row_dedupe_key(row: dict[str, Any]) -> str:
    return _session_display.service(RUNTIME).session_row_dedupe_key(row)


def _display_source_path(s: Session) -> str | None:
    return _session_display.service(RUNTIME).display_source_path(s)


def _durable_session_id_for_live_session(s: Session) -> str:
    return _session_display.service(RUNTIME).durable_session_id_for_live_session(s)


def _display_pi_busy(s: Session, *, broker_busy: bool) -> bool:
    return _session_display.service(RUNTIME).display_pi_busy(s, broker_busy=broker_busy)


def _validated_session_state(state: dict[str, Any] | Any) -> dict[str, Any]:
    return _session_display.service(RUNTIME).validated_session_state(state)


def _state_busy_value(state: dict[str, Any]) -> bool:
    return _session_display.service(RUNTIME).state_busy_value(state)


def _state_queue_len_value(state: dict[str, Any]) -> int:
    return _session_display.service(RUNTIME).state_queue_len_value(state)


def _display_session_busy(
    manager: "SessionManager", session_id: str, s: Session, state: dict[str, Any]
) -> tuple[bool, bool]:
    return _session_display.service(RUNTIME).display_session_busy(
        manager,
        session_id,
        s,
        state,
    )


def _resolved_session_run_settings(
    s: Session,
) -> tuple[str | None, str | None, str | None, str | None]:
    return _session_display.service(RUNTIME).resolved_session_run_settings(s)


def _resolved_session_token(
    s: Session, token: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    return _session_display.service(RUNTIME).resolved_session_token(s, token=token)


def _session_context_usage_payload(
    s: Session, token_val: dict[str, Any] | None
) -> dict[str, Any] | None:
    return _session_payloads.service(RUNTIME).session_context_usage_payload(s, token_val)


def _session_turn_timing_payload(
    s: Session,
    events: list[dict[str, Any]],
    *,
    busy: bool,
) -> dict[str, Any] | None:
    return _session_payloads.service(RUNTIME).session_turn_timing_payload(s, events, busy=busy)


def _session_workspace_payload(
    manager: "SessionManager", session_id: str
) -> dict[str, Any]:
    return _session_payloads.service(RUNTIME, manager).session_workspace_payload(session_id)


def _session_live_payload(
    manager: "SessionManager",
    session_id: str,
    *,
    offset: int = 0,
    live_offset: int = 0,
    bridge_offset: int = 0,
    requests_version: str | None = None,
) -> dict[str, Any]:
    return _session_live_payloads.service(RUNTIME, manager).session_live_payload(session_id, offset=offset, live_offset=live_offset, bridge_offset=bridge_offset, requests_version=requests_version)


def _supports_web_control(meta: dict[str, Any]) -> bool:
    return meta.get("supports_web_control") is True


def _build_runtime_api() -> RuntimeApi:
    return RuntimeApi(sys.modules[__name__], exports=_RUNTIME_API_EXPORTS)


class SessionManager(_manager_delegates.SessionManagerDelegates):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Sidebar should reflect broker-visible live sessions only.
        self._include_historical_sessions = False
        self._bad_sidecars: dict[str, tuple[bool, int, int]] = {}
        self._sessions: dict[str, Session] = {}
        self._stop = threading.Event()
        self._last_discover_ts = 0.0
        self._last_session_catalog_refresh_ts = 0.0
        self._page_state_db = PageStateDB(PAGE_STATE_DB_PATH)
        if self._page_state_db.is_empty():
            import_legacy_app_dir_to_db(source_app_dir=APP_DIR, db_path=PAGE_STATE_DB_PATH)
        self._harness: dict[str, dict[str, Any]] = {}
        self._aliases: dict[SessionStateKey, str] = {}
        self._sidebar_meta: dict[SessionStateKey, dict[str, Any]] = {}
        self._hidden_sessions: set[str] = set()
        self._files: dict[SessionStateKey, list[str]] = {}
        self._queues: dict[SessionStateKey, list[str]] = {}
        self._bridge_events: dict[str, list[dict[str, Any]]] = {}
        self._bridge_event_offsets: dict[str, int] = {}
        self._outbound_requests: dict[str, list[BridgeOutboundRequest]] = {}
        self._queue_wakeup = threading.Event()
        self._pi_commands_cache: dict[str, dict[str, Any]] = {}
        self._recent_cwds: dict[str, float] = {}
        self._cwd_groups: dict[str, dict[str, Any]] = {}
        self._prune_missing_workspace_dirs = True
        self._runtime = build_server_runtime(
            sys.modules[__name__],
            manager=self,
            event_hub=EVENT_HUB,
            api=_build_runtime_api(),
        )
        globals()["MANAGER"] = self
        globals()["RUNTIME"] = self._runtime
        self._sidebar_state = SidebarStateFacade(self)
        self._harness_last_injected: dict[str, float] = {}
        self._harness_last_injected_scope: dict[str, float] = {}
        self._load_harness()
        self._load_aliases()
        self._load_sidebar_meta()
        self._load_hidden_sessions()
        self._load_files()
        self._load_queues()
        self._load_recent_cwds()
        self._load_cwd_groups()
        self._voice_push = VoicePushCoordinator(
            app_dir=APP_DIR,
            stop_event=self._stop,
            settings_path=VOICE_SETTINGS_PATH,
            subscriptions_path=PUSH_SUBSCRIPTIONS_PATH,
            delivery_ledger_path=DELIVERY_LEDGER_PATH,
            vapid_private_key_path=VAPID_PRIVATE_KEY_PATH,
            page_state_db=self._page_state_db,
            publish_callback=_voice_push_publish_callback,
        )
        self._discover_existing(force=True, skip_invalid_sidecars=True)
        self._refresh_durable_session_catalog(force=True)
        self._harness_thr = threading.Thread(
            target=self._harness_loop, name="harness", daemon=True
        )
        self._harness_thr.start()
        self._queue_thr = threading.Thread(
            target=self._queue_loop, name="queue", daemon=True
        )
        self._queue_thr.start()
        self._voice_push_scan_thr = threading.Thread(
            target=self._voice_push_scan_loop, name="voice-push-scan", daemon=True
        )
        self._voice_push_scan_thr.start()

    def _sidebar_state_facade(self) -> SidebarStateFacade:
        if getattr(self, "_runtime", None) is None:
            self._runtime = RUNTIME
        facade = getattr(self, "_sidebar_state", None)
        if isinstance(facade, SidebarStateFacade):
            return facade
        facade = SidebarStateFacade(self)
        self._sidebar_state = facade
        return facade

    def stop(self) -> None:
        self._stop.set()
        EVENT_HUB.close()

    def get_ui_state(self, session_id: str) -> dict[str, Any]:
        return _pi_ui_bridge.get_ui_state(RUNTIME, self, session_id)

    def get_session_commands(self, session_id: str) -> dict[str, Any]:
        return _pi_ui_bridge.get_session_commands(RUNTIME, self, session_id)

    def submit_ui_response(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return _pi_ui_bridge.submit_ui_response(RUNTIME, self, session_id, payload)

MANAGER = SessionManager()
RUNTIME = MANAGER._runtime


def _read_static_bytes(path: Path) -> bytes:
    return _http_static_assets.read_static_bytes(RUNTIME, path)


def _is_path_within(root: Path, candidate: Path) -> bool:
    return _http_static_assets.is_path_within(root, candidate)


def _served_web_dist_dir() -> Path | None:
    return _http_static_assets.served_web_dist_dir(RUNTIME)


def _asset_version_from_manifest(manifest: dict[str, object]) -> str:
    return _http_static_assets.asset_version_from_manifest(manifest)


def _pi_model_context_window(provider: str | None, model: str | None) -> int | None:
    return _pi_model_context_window_impl(provider, model)


def _read_web_index() -> tuple[str, str]:
    return _http_static_assets.read_web_index(RUNTIME)


def _resolve_public_web_asset(rel: str) -> Path | None:
    return _http_static_assets.resolve_public_web_asset(RUNTIME, rel)


def _content_type_for_path(path: Path) -> str:
    return _http_static_assets.content_type_for_path(path)


def _cache_control_for_path(path: Path) -> str:
    return _http_static_assets.cache_control_for_path(path)


Handler = _http_server_runner.make_handler(RUNTIME)
ThreadingHTTPServer = _http_server_runner.ThreadingHTTPServer
ThreadingHTTPServerV6 = _http_server_runner.ThreadingHTTPServerV6


def main() -> None:
    _http_server_runner.main(RUNTIME, Handler)


if __name__ == "__main__":
    main()
