from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any


def ensure_tmux_short_app_dir(runtime: Any) -> str:
    try:
        runtime.APP_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        return str(runtime.TMUX_SHORT_APP_DIR)

    alias = runtime.TMUX_SHORT_APP_DIR
    try:
        if alias.is_symlink():
            if alias.resolve() == runtime.APP_DIR.resolve():
                return str(alias)
            alias.unlink()
        elif alias.exists():
            if alias.resolve() == runtime.APP_DIR.resolve():
                return str(alias)
            return str(alias)
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.symlink_to(runtime.APP_DIR, target_is_directory=True)
        return str(alias)
    except Exception:
        return str(alias)


def wait_for_spawned_broker_meta(
    runtime: Any,
    spawn_nonce: str,
    *,
    timeout_s: float,
) -> dict[str, Any]:
    deadline = time.time() + max(timeout_s, 0.0)
    last_meta: dict[str, Any] | None = None
    while time.time() <= deadline:
        for meta_path in sorted(runtime.SOCK_DIR.glob("*.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                continue
            if not isinstance(meta, dict):
                continue
            if runtime._clean_optional_text(meta.get("spawn_nonce")) != spawn_nonce:
                continue
            broker_pid = meta.get("broker_pid")
            if not isinstance(broker_pid, int):
                continue
            last_meta = meta
            backend = runtime.normalize_agent_backend(meta.get("backend"), default="codex")
            session_id = runtime._clean_optional_text(meta.get("session_id"))
            if backend == "pi" and session_id is None:
                continue
            return meta
        time.sleep(0.05)
    if last_meta is not None:
        return last_meta
    raise RuntimeError(
        f"tmux launch did not publish broker metadata within {timeout_s:.1f}s"
    )


def create_git_worktree(runtime: Any, source_cwd: Path, worktree_branch: str) -> Path:
    repo_root = runtime._git_repo_root(source_cwd)
    if repo_root is None:
        raise ValueError("cwd is not inside a git worktree")
    branch = runtime._clean_worktree_branch(worktree_branch)
    target = runtime._default_worktree_path(source_cwd, branch)
    if target.exists():
        raise ValueError(f"derived worktree path already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(target)],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=runtime.GIT_WORKTREE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("git worktree add timed out") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        raise ValueError(err or out or f"git worktree add failed with code {proc.returncode}")
    return target.resolve()


def parse_git_numstat(text: str) -> dict[str, dict[str, int | None]]:
    out: dict[str, dict[str, int | None]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        add_raw, del_raw, path = parts
        path_s = path.strip()
        if not path_s:
            continue
        add_v = None if add_raw == "-" else int(add_raw)
        del_v = None if del_raw == "-" else int(del_raw)
        prev = out.get(path_s)
        if prev is None:
            out[path_s] = {"additions": add_v, "deletions": del_v}
            continue
        if add_v is None or prev["additions"] is None:
            prev["additions"] = None
        else:
            prev["additions"] = int(prev["additions"]) + add_v
        if del_v is None or prev["deletions"] is None:
            prev["deletions"] = None
        else:
            prev["deletions"] = int(prev["deletions"]) + del_v
    return out
