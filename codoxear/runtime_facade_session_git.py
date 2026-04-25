from __future__ import annotations

from pathlib import Path
from typing import Any


class RuntimeFacadeSessionGitMixin:
    def _session_git_cwd(self, session_id: str) -> Path:
        self.manager.refresh_session_meta(session_id, strict=False)
        session = self.manager.get_session(session_id)
        if not session:
            raise KeyError("unknown session")
        cwd = self.api.safe_expanduser(Path(session.cwd))
        if not cwd.is_absolute():
            cwd = cwd.resolve()
        self.api.require_git_repo(cwd)
        return cwd

    def _normalize_git_list(self, rows: list[str]) -> list[str]:
        out: list[str] = []
        for row in rows:
            text = row.strip()
            if not text:
                continue
            out.append(text)
            if len(out) >= self.api.GIT_CHANGED_FILES_MAX:
                break
        return out

    def session_git_changed_files_payload(self, session_id: str) -> dict[str, Any]:
        cwd = self._session_git_cwd(session_id)
        unstaged = self.api.run_git(
            cwd,
            ["diff", "--name-only"],
            timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=64 * 1024,
        ).splitlines()
        staged = self.api.run_git(
            cwd,
            ["diff", "--name-only", "--cached"],
            timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=64 * 1024,
        ).splitlines()
        unstaged_numstat = self.api.run_git(
            cwd,
            ["diff", "--numstat"],
            timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=128 * 1024,
        )
        staged_numstat = self.api.run_git(
            cwd,
            ["diff", "--numstat", "--cached"],
            timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=128 * 1024,
        )
        unstaged2 = self._normalize_git_list(unstaged)
        staged2 = self._normalize_git_list(staged)
        seen: set[str] = set()
        merged: list[str] = []
        for row in [*unstaged2, *staged2]:
            if row in seen:
                continue
            seen.add(row)
            merged.append(row)
        spawn_utils = self.api.spawn_utils.service(self.runtime)
        stats = spawn_utils.parse_git_numstat(unstaged_numstat)
        for path_key, vals in spawn_utils.parse_git_numstat(staged_numstat).items():
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
        return {
            "ok": True,
            "cwd": str(cwd),
            "files": merged,
            "entries": entries,
            "unstaged": unstaged2,
            "staged": staged2,
        }

    def session_git_diff_payload(
        self,
        session_id: str,
        *,
        rel_path: str,
        staged: bool,
    ) -> dict[str, Any]:
        cwd = self._session_git_cwd(session_id)
        _target, _repo_root, rel = self.api.resolve_git_path(cwd, rel_path)
        args = ["diff", "-U3"]
        if staged:
            args.append("--cached")
        args.extend(["--", rel])
        diff = self.api.run_git(
            cwd,
            args,
            timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
            max_bytes=self.api.GIT_DIFF_MAX_BYTES,
        )
        return {
            "ok": True,
            "cwd": str(cwd),
            "path": rel,
            "staged": staged,
            "diff": diff,
        }

    def session_git_file_versions_payload(
        self,
        session_id: str,
        *,
        rel_path: str,
    ) -> dict[str, Any]:
        cwd = self._session_git_cwd(session_id)
        path_obj, _repo_root, rel = self.api.resolve_git_path(cwd, rel_path)
        current_text = ""
        current_size = 0
        current_exists = bool(path_obj.exists() and path_obj.is_file())
        if current_exists:
            current_text, current_size = self.api.read_text_file_strict(
                path_obj,
                max_bytes=self.api.FILE_READ_MAX_BYTES,
            )
        try:
            self.manager.files_add(session_id, str(path_obj))
        except KeyError:
            pass
        base_exists = False
        base_text = ""
        try:
            base_text = self.api.run_git(
                cwd,
                ["show", f"HEAD:{rel}"],
                timeout_s=self.api.GIT_DIFF_TIMEOUT_SECONDS,
                max_bytes=self.api.FILE_READ_MAX_BYTES,
            )
            base_exists = True
        except RuntimeError:
            base_exists = False
            base_text = ""
        return {
            "ok": True,
            "cwd": str(cwd),
            "path": rel,
            "abs_path": str(path_obj),
            "current_exists": current_exists,
            "current_size": int(current_size),
            "current_text": current_text,
            "base_exists": base_exists,
            "base_text": base_text,
        }
