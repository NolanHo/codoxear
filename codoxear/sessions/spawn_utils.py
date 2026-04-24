from __future__ import annotations

import json
import subprocess
import time
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
class SpawnUtilsService:
    runtime: ServerRuntime

    def ensure_tmux_short_app_dir(self) -> str:
        wrapper = _runtime_wrapper(self.runtime, "_ensure_tmux_short_app_dir")
        if wrapper is not None:
            return wrapper()
        return ensure_tmux_short_app_dir(self.runtime)

    def wait_for_spawned_broker_meta(
        self,
        spawn_nonce: str,
        *,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        wrapper = _runtime_wrapper(self.runtime, "_wait_for_spawned_broker_meta")
        if wrapper is not None:
            if timeout_s is None:
                return wrapper(spawn_nonce)
            return wrapper(spawn_nonce, timeout_s=timeout_s)
        resolved_timeout = (
            float(self.runtime.api.TMUX_META_WAIT_SECONDS)
            if timeout_s is None
            else float(timeout_s)
        )
        return wait_for_spawned_broker_meta(
            self.runtime,
            spawn_nonce,
            timeout_s=resolved_timeout,
        )

    def wait_or_raise(
        self,
        proc: subprocess.Popen[bytes],
        *,
        label: str,
        timeout_s: float = 1.5,
    ) -> None:
        wrapper = _runtime_wrapper(self.runtime, "_wait_or_raise")
        if wrapper is not None:
            return wrapper(proc, label=label, timeout_s=timeout_s)
        return wait_or_raise(proc, label=label, timeout_s=timeout_s)

    def spawn_result_from_meta(self, meta: dict[str, Any]) -> dict[str, Any]:
        wrapper = _runtime_wrapper(self.runtime, "_spawn_result_from_meta")
        if wrapper is not None:
            return wrapper(meta)
        return spawn_result_from_meta(self.runtime, meta)

    def create_git_worktree(self, source_cwd: Path, worktree_branch: str) -> Path:
        wrapper = _runtime_wrapper(self.runtime, "_create_git_worktree")
        if wrapper is not None:
            return wrapper(source_cwd, worktree_branch)
        return create_git_worktree(self.runtime, source_cwd, worktree_branch)

    def parse_git_numstat(self, text: str) -> dict[str, dict[str, int | None]]:
        wrapper = _runtime_wrapper(self.runtime, "_parse_git_numstat")
        if wrapper is not None:
            return wrapper(text)
        return parse_git_numstat(text)


def service(runtime: ServerRuntime) -> SpawnUtilsService:
    return SpawnUtilsService(runtime)


def ensure_tmux_short_app_dir(runtime: Any) -> str:
    try:
        runtime.api.APP_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        return str(runtime.api.TMUX_SHORT_APP_DIR)

    alias = runtime.api.TMUX_SHORT_APP_DIR
    try:
        if alias.is_symlink():
            if alias.resolve() == runtime.api.APP_DIR.resolve():
                return str(alias)
            alias.unlink()
        elif alias.exists():
            if alias.resolve() == runtime.api.APP_DIR.resolve():
                return str(alias)
            return str(alias)
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.symlink_to(runtime.api.APP_DIR, target_is_directory=True)
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
        for meta_path in sorted(runtime.api.SOCK_DIR.glob("*.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                continue
            if not isinstance(meta, dict):
                continue
            if runtime.api.clean_optional_text(meta.get("spawn_nonce")) != spawn_nonce:
                continue
            broker_pid = meta.get("broker_pid")
            if not isinstance(broker_pid, int):
                continue
            last_meta = meta
            backend = runtime.api.normalize_agent_backend(meta.get("backend"), default="codex")
            session_id = runtime.api.clean_optional_text(meta.get("session_id"))
            if backend == "pi" and session_id is None:
                continue
            return meta
        time.sleep(0.05)
    if last_meta is not None:
        return last_meta
    raise RuntimeError(
        f"tmux launch did not publish broker metadata within {timeout_s:.1f}s"
    )


def wait_or_raise(
    proc: subprocess.Popen[bytes], *, label: str, timeout_s: float = 1.5
) -> None:
    deadline = time.time() + float(timeout_s)
    while time.time() < deadline:
        rc = proc.poll()
        if rc is None:
            time.sleep(0.05)
            continue
        _out, err = proc.communicate(timeout=0.5)
        err2 = err if isinstance(err, (bytes, bytearray)) else b""
        msg = bytes(err2).decode("utf-8", errors="replace").strip()
        msg = msg[-4000:] if msg else ""
        raise RuntimeError(f"{label} exited early (rc={rc}): {msg}")


def spawn_result_from_meta(runtime: Any, meta: dict[str, Any]) -> dict[str, Any]:
    broker_pid = meta.get("broker_pid")
    if not isinstance(broker_pid, int):
        raise RuntimeError("spawn metadata is missing broker_pid")
    sock_path = runtime.api.clean_optional_text(meta.get("sock_path"))
    runtime_id = Path(sock_path).stem if sock_path else None
    session_id = runtime.api.clean_optional_text(meta.get("session_id")) or runtime_id
    payload: dict[str, Any] = {"broker_pid": int(broker_pid)}
    if session_id:
        payload["session_id"] = session_id
    if runtime_id:
        payload["runtime_id"] = runtime_id
    backend = runtime.api.clean_optional_text(meta.get("backend"))
    if backend:
        payload["backend"] = backend
    return payload


def create_git_worktree(runtime: Any, source_cwd: Path, worktree_branch: str) -> Path:
    repo_root = runtime.api.git_repo_root(source_cwd)
    if repo_root is None:
        raise ValueError("cwd is not inside a git worktree")
    branch = runtime.api.clean_worktree_branch(worktree_branch)
    target = runtime.api.default_worktree_path(source_cwd, branch)
    if target.exists():
        raise ValueError(f"derived worktree path already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(target)],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=runtime.api.GIT_WORKTREE_TIMEOUT_SECONDS,
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
