import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from codoxear.sessions import spawn_utils as _spawn_utils
from codoxear.runtime_facade_session_git import RuntimeFacadeSessionGitMixin
from codoxear.workspace import file_access as _file_access


class _Session:
    def __init__(self, cwd: str) -> None:
        self.cwd = cwd


class _Manager:
    def __init__(self, session: _Session | None) -> None:
        self.session = session
        self.refresh_calls: list[tuple[str, bool]] = []
        self.files_add_calls: list[tuple[str, str]] = []
        self.files_add_error: Exception | None = None

    def refresh_session_meta(self, session_id: str, strict: bool = False) -> None:
        self.refresh_calls.append((session_id, strict))

    def get_session(self, session_id: str) -> _Session | None:
        if session_id != "session-1":
            return None
        return self.session

    def files_add(self, session_id: str, path: str) -> None:
        self.files_add_calls.append((session_id, path))
        if self.files_add_error is not None:
            raise self.files_add_error


class _Api:
    GIT_CHANGED_FILES_MAX = 2
    GIT_DIFF_TIMEOUT_SECONDS = 2.0
    GIT_DIFF_MAX_BYTES = 64 * 1024
    FILE_READ_MAX_BYTES = 64 * 1024
    spawn_utils = _spawn_utils

    def __init__(self) -> None:
        self.require_git_repo_calls: list[Path] = []
        self.resolve_git_path_calls: list[tuple[Path, str]] = []
        self.read_text_file_strict_calls: list[tuple[Path, int]] = []
        self.run_git_calls: list[tuple[Path, list[str], float, int]] = []
        self.require_git_repo_impl = lambda _cwd: None
        self.resolve_git_path_result: tuple[Path, Path, str] | None = None
        self.run_git_results: list[str | Exception] = []

    def safe_expanduser(self, path: Path) -> Path:
        try:
            return path.expanduser()
        except RuntimeError:
            return path

    def require_git_repo(self, cwd: Path) -> None:
        self.require_git_repo_calls.append(cwd)
        self.require_git_repo_impl(cwd)

    def resolve_git_path(self, cwd: Path, raw_path: str) -> tuple[Path, Path, str]:
        self.resolve_git_path_calls.append((cwd, raw_path))
        if self.resolve_git_path_result is not None:
            return self.resolve_git_path_result
        repo_root = Path(
            self.run_git(
                cwd,
                ["rev-parse", "--show-toplevel"],
                timeout_s=self.GIT_DIFF_TIMEOUT_SECONDS,
                max_bytes=64 * 1024,
            ).strip()
        ).resolve()
        target = self._resolve_session_path(cwd, raw_path)
        try:
            rel = str(target.relative_to(repo_root))
        except ValueError as exc:
            raise ValueError("path is outside git repo") from exc
        return target, repo_root, rel

    def read_text_file_strict(self, path: Path, *, max_bytes: int) -> tuple[str, int]:
        self.read_text_file_strict_calls.append((path, max_bytes))
        return _file_access.read_text_file_strict(path, max_bytes=max_bytes)

    def run_git(self, cwd: Path, args: list[str], *, timeout_s: float, max_bytes: int) -> str:
        self.run_git_calls.append((cwd, list(args), timeout_s, max_bytes))
        if self.run_git_results:
            result = self.run_git_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        proc = subprocess.run(
            ["git", *args],
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

    def _resolve_session_path(self, base: Path, raw_path: str) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("path required")
        if "\x00" in raw_path:
            raise ValueError("invalid path")
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return self.safe_expanduser(candidate).resolve()
        resolved_base = self.safe_expanduser(base)
        if not resolved_base.is_absolute():
            resolved_base = resolved_base.resolve()
        return (resolved_base / candidate).resolve()


class _Facade(RuntimeFacadeSessionGitMixin):
    def __init__(self, api: _Api, manager: _Manager) -> None:
        self.runtime = SimpleNamespace(module=None, api=api)
        self._api = api
        self._manager = manager

    @property
    def api(self) -> _Api:
        return self._api

    @property
    def manager(self) -> _Manager:
        return self._manager


class TestRuntimeFacadeSessionGitMixin(unittest.TestCase):
    def test_session_git_cwd_raises_for_unknown_session(self) -> None:
        api = _Api()
        manager = _Manager(None)
        facade = _Facade(api, manager)

        with self.assertRaisesRegex(KeyError, "unknown session"):
            facade._session_git_cwd("missing")

        self.assertEqual(manager.refresh_calls, [("missing", False)])
        self.assertEqual(api.require_git_repo_calls, [])

    def test_normalize_git_list_strips_blanks_and_caps_length(self) -> None:
        facade = _Facade(_Api(), _Manager(_Session(".")))

        self.assertEqual(
            facade._normalize_git_list([" alpha.py ", "", "beta.py", "gamma.py"]),
            ["alpha.py", "beta.py"],
        )

    def test_changed_files_payload_merges_unique_paths_and_numstat(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            api = _Api()
            api.run_git_results = [
                " alpha.txt \nshared.txt\n",
                "shared.txt\nbeta.txt\n",
                "1\t0\talpha.txt\n2\t1\tshared.txt\n",
                "5\t0\tshared.txt\n3\t4\tbeta.txt\n",
            ]
            manager = _Manager(_Session(td))
            facade = _Facade(api, manager)

            payload = facade.session_git_changed_files_payload("session-1")

        self.assertEqual(api.require_git_repo_calls, [Path(td).resolve()])
        self.assertEqual(
            [call[1] for call in api.run_git_calls],
            [
                ["diff", "--name-only"],
                ["diff", "--name-only", "--cached"],
                ["diff", "--numstat"],
                ["diff", "--numstat", "--cached"],
            ],
        )
        self.assertEqual(payload["files"], ["alpha.txt", "shared.txt", "beta.txt"])
        self.assertEqual(payload["unstaged"], ["alpha.txt", "shared.txt"])
        self.assertEqual(payload["staged"], ["shared.txt", "beta.txt"])
        self.assertEqual(
            payload["entries"],
            [
                {"path": "alpha.txt", "additions": 1, "deletions": 0, "changed": True},
                {"path": "shared.txt", "additions": 7, "deletions": 1, "changed": True},
                {"path": "beta.txt", "additions": 3, "deletions": 4, "changed": True},
            ],
        )

    def test_diff_payload_uses_normalized_repo_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            target = repo / "src" / "app.py"
            api = _Api()
            api.resolve_git_path_result = (target, repo, "src/app.py")
            api.run_git_results = ["patch body"]
            manager = _Manager(_Session(str(repo)))
            facade = _Facade(api, manager)

            payload = facade.session_git_diff_payload(
                "session-1",
                rel_path="./src/../src/app.py",
                staged=True,
            )

        self.assertEqual(api.resolve_git_path_calls, [(repo, "./src/../src/app.py")])
        self.assertEqual(
            api.run_git_calls,
            [
                (
                    repo,
                    ["diff", "-U3", "--cached", "--", "src/app.py"],
                    api.GIT_DIFF_TIMEOUT_SECONDS,
                    api.GIT_DIFF_MAX_BYTES,
                )
            ],
        )
        self.assertEqual(
            payload,
            {
                "ok": True,
                "cwd": str(repo),
                "path": "src/app.py",
                "staged": True,
                "diff": "patch body",
            },
        )

    def test_file_versions_payload_reads_current_and_base_versions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            current = repo / "notes.txt"
            current.write_text("current text\n", encoding="utf-8")
            api = _Api()
            api.resolve_git_path_result = (current, repo, "notes.txt")
            api.run_git_results = ["base text\n"]
            manager = _Manager(_Session(str(repo)))
            facade = _Facade(api, manager)

            payload = facade.session_git_file_versions_payload("session-1", rel_path="notes.txt")

        self.assertEqual(api.read_text_file_strict_calls, [(current, api.FILE_READ_MAX_BYTES)])
        self.assertEqual(
            api.run_git_calls,
            [
                (
                    repo,
                    ["show", "HEAD:notes.txt"],
                    api.GIT_DIFF_TIMEOUT_SECONDS,
                    api.FILE_READ_MAX_BYTES,
                )
            ],
        )
        self.assertEqual(manager.files_add_calls, [("session-1", str(current))])
        self.assertEqual(payload["current_text"], "current text\n")
        self.assertEqual(payload["current_size"], len("current text\n"))
        self.assertTrue(payload["current_exists"])
        self.assertTrue(payload["base_exists"])
        self.assertEqual(payload["base_text"], "base text\n")
        self.assertEqual(payload["abs_path"], str(current))

    def test_file_versions_payload_ignores_missing_history_registration(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            current = repo / "draft.txt"
            current.write_text("draft\n", encoding="utf-8")
            api = _Api()
            api.resolve_git_path_result = (current, repo, "draft.txt")
            api.run_git_results = [RuntimeError("missing from HEAD")]
            manager = _Manager(_Session(str(repo)))
            manager.files_add_error = KeyError("missing session history")
            facade = _Facade(api, manager)

            payload = facade.session_git_file_versions_payload("session-1", rel_path="draft.txt")

        self.assertEqual(manager.files_add_calls, [("session-1", str(current))])
        self.assertTrue(payload["current_exists"])
        self.assertFalse(payload["base_exists"])
        self.assertEqual(payload["base_text"], "")


if __name__ == "__main__":
    unittest.main()
