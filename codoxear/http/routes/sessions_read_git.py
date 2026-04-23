from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

from ...runtime import ServerRuntime
from . import sessions_read_common as _common


def _normalize_list(runtime: ServerRuntime, rows: list[str]) -> list[str]:
    out: list[str] = []
    for row in rows:
        text = row.strip()
        if not text:
            continue
        out.append(text)
        if len(out) >= runtime.api.GIT_CHANGED_FILES_MAX:
            break
    return out


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    if path.startswith("/api/sessions/") and path.endswith("/git/changed_files"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        runtime.manager.refresh_session_meta(session_id, strict=False)
        s = runtime.manager.get_session(session_id)
        if not s:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        cwd = runtime.api.safe_expanduser(Path(s.cwd))
        if not cwd.is_absolute():
            cwd = cwd.resolve()
        try:
            runtime.api.require_git_repo(cwd)
        except RuntimeError as exc:
            runtime.api.json_response(handler, 409, {"error": str(exc)})
            return True
        unstaged = runtime.api.run_git(
            cwd,
            ["diff", "--name-only"],
            timeout_s=runtime.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=64 * 1024,
        ).splitlines()
        staged = runtime.api.run_git(
            cwd,
            ["diff", "--name-only", "--cached"],
            timeout_s=runtime.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=64 * 1024,
        ).splitlines()
        unstaged_numstat = runtime.api.run_git(
            cwd,
            ["diff", "--numstat"],
            timeout_s=runtime.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=128 * 1024,
        )
        staged_numstat = runtime.api.run_git(
            cwd,
            ["diff", "--numstat", "--cached"],
            timeout_s=runtime.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=128 * 1024,
        )
        unstaged2 = _normalize_list(runtime, unstaged)
        staged2 = _normalize_list(runtime, staged)
        seen: set[str] = set()
        merged: list[str] = []
        for row in [*unstaged2, *staged2]:
            if row in seen:
                continue
            seen.add(row)
            merged.append(row)
        stats = runtime.api.parse_git_numstat(unstaged_numstat)
        for path_key, vals in runtime.api.parse_git_numstat(staged_numstat).items():
            prev = stats.get(path_key)
            if prev is None:
                stats[path_key] = vals
                continue
            add_prev = prev.get("additions")
            del_prev = prev.get("deletions")
            add_new = vals.get("additions")
            del_new = vals.get("deletions")
            prev["additions"] = (
                None if add_prev is None or add_new is None else int(add_prev) + int(add_new)
            )
            prev["deletions"] = (
                None if del_prev is None or del_new is None else int(del_prev) + int(del_new)
            )
        entries: list[dict[str, Any]] = []
        for path_key in merged:
            vals = stats.get(path_key, {})
            entries.append(
                {
                    "path": path_key,
                    "additions": vals.get("additions"),
                    "deletions": vals.get("deletions"),
                    "changed": True,
                }
            )
        runtime.api.json_response(
            handler,
            200,
            {
                "ok": True,
                "cwd": str(cwd),
                "files": merged,
                "entries": entries,
                "unstaged": unstaged2,
                "staged": staged2,
            },
        )
        return True

    if path.startswith("/api/sessions/") and path.endswith("/git/diff"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        runtime.manager.refresh_session_meta(session_id, strict=False)
        s = runtime.manager.get_session(session_id)
        if not s:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        qs = urllib.parse.parse_qs(u.query)
        path_q = qs.get("path")
        if not path_q or not path_q[0]:
            runtime.api.json_response(handler, 400, {"error": "path required"})
            return True
        rel = path_q[0]
        staged_q = qs.get("staged")
        staged = bool(staged_q and staged_q[0] == "1")
        cwd = runtime.api.safe_expanduser(Path(s.cwd))
        if not cwd.is_absolute():
            cwd = cwd.resolve()
        try:
            runtime.api.require_git_repo(cwd)
        except RuntimeError as exc:
            runtime.api.json_response(handler, 409, {"error": str(exc)})
            return True
        try:
            _target, _repo_root, rel = runtime.api.resolve_git_path(cwd, rel)
        except ValueError as exc:
            runtime.api.json_response(handler, 400, {"error": str(exc)})
            return True
        args = ["diff", "-U3"]
        if staged:
            args.append("--cached")
        args.extend(["--", rel])
        diff = runtime.api.run_git(
            cwd,
            args,
            timeout_s=runtime.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=runtime.api.GIT_DIFF_MAX_BYTES,
        )
        runtime.api.json_response(
            handler,
            200,
            {
                "ok": True,
                "cwd": str(cwd),
                "path": rel,
                "staged": staged,
                "diff": diff,
            },
        )
        return True

    if path.startswith("/api/sessions/") and path.endswith("/git/file_versions"):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        runtime.manager.refresh_session_meta(session_id, strict=False)
        s = runtime.manager.get_session(session_id)
        if not s:
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        qs = urllib.parse.parse_qs(u.query)
        path_q = qs.get("path")
        if not path_q or not path_q[0]:
            runtime.api.json_response(handler, 400, {"error": "path required"})
            return True
        rel = path_q[0]
        cwd = runtime.api.safe_expanduser(Path(s.cwd))
        if not cwd.is_absolute():
            cwd = cwd.resolve()
        try:
            runtime.api.require_git_repo(cwd)
        except RuntimeError as exc:
            runtime.api.json_response(handler, 409, {"error": str(exc)})
            return True
        try:
            p, _repo_root, rel = runtime.api.resolve_git_path(cwd, rel)
        except ValueError as exc:
            runtime.api.json_response(handler, 400, {"error": str(exc)})
            return True
        current_text = ""
        current_size = 0
        current_exists = bool(p.exists() and p.is_file())
        if current_exists:
            current_text, current_size = runtime.api.read_text_file_strict(
                p,
                max_bytes=runtime.api.FILE_READ_MAX_BYTES,
            )
        try:
            runtime.manager.files_add(session_id, str(p))
        except KeyError:
            pass
        base_exists = False
        base_text = ""
        try:
            base_text = runtime.api.run_git(
                cwd,
                ["show", f"HEAD:{rel}"],
                timeout_s=runtime.api.GIT_DIFF_TIMEOUT_SECONDS,
                max_bytes=runtime.api.FILE_READ_MAX_BYTES,
            )
            base_exists = True
        except RuntimeError:
            base_exists = False
            base_text = ""
        runtime.api.json_response(
            handler,
            200,
            {
                "ok": True,
                "cwd": str(cwd),
                "path": rel,
                "abs_path": str(p),
                "current_exists": current_exists,
                "current_size": int(current_size),
                "current_text": current_text,
                "base_exists": base_exists,
                "base_text": base_text,
            },
        )
        return True

    return False
