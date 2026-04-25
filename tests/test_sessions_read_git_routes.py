import urllib.parse
import unittest
from typing import Any
from unittest.mock import patch

from codoxear.http.routes import sessions_read_git as routes


class _Handler:
    def __init__(self) -> None:
        self.responses: list[tuple[int, dict[str, Any]]] = []
        self.unauthorized_called = False
        self.sent_error: int | None = None

    def _unauthorized(self) -> None:
        self.unauthorized_called = True

    def send_error(self, status: int) -> None:
        self.sent_error = status


class _Facade:
    def __init__(self) -> None:
        self.require_auth_result = True
        self.changed_files_result: dict[str, Any] | Exception = {"ok": True, "files": []}
        self.diff_result: dict[str, Any] | Exception = {"ok": True, "diff": ""}
        self.file_versions_result: dict[str, Any] | Exception = {"ok": True, "base_text": ""}
        self.changed_files_calls: list[str] = []
        self.diff_calls: list[tuple[str, str, bool]] = []
        self.file_versions_calls: list[tuple[str, str]] = []

    def require_auth(self, handler: Any) -> bool:
        return self.require_auth_result

    def json_response(self, handler: _Handler, status: int, payload: dict[str, Any]) -> None:
        handler.responses.append((status, payload))

    def session_git_changed_files_payload(self, session_id: str) -> dict[str, Any]:
        self.changed_files_calls.append(session_id)
        if isinstance(self.changed_files_result, Exception):
            raise self.changed_files_result
        return self.changed_files_result

    def session_git_diff_payload(
        self,
        session_id: str,
        *,
        rel_path: str,
        staged: bool,
    ) -> dict[str, Any]:
        self.diff_calls.append((session_id, rel_path, staged))
        if isinstance(self.diff_result, Exception):
            raise self.diff_result
        return self.diff_result

    def session_git_file_versions_payload(
        self,
        session_id: str,
        *,
        rel_path: str,
    ) -> dict[str, Any]:
        self.file_versions_calls.append((session_id, rel_path))
        if isinstance(self.file_versions_result, Exception):
            raise self.file_versions_result
        return self.file_versions_result


class TestSessionsReadGitRoutes(unittest.TestCase):
    def test_changed_files_route_returns_facade_payload(self) -> None:
        facade = _Facade()
        facade.changed_files_result = {"ok": True, "files": ["tracked.py"]}
        handler = _Handler()
        u = urllib.parse.urlparse("/api/sessions/session-1/git/changed_files")

        with patch.object(routes, "build_runtime_facade", return_value=facade):
            handled = routes.handle_get(object(), handler, u.path, u)

        self.assertTrue(handled)
        self.assertEqual(facade.changed_files_calls, ["session-1"])
        self.assertEqual(handler.responses, [(200, {"ok": True, "files": ["tracked.py"]})])

    def test_changed_files_route_rejects_unauthorized_requests(self) -> None:
        facade = _Facade()
        facade.require_auth_result = False
        handler = _Handler()
        u = urllib.parse.urlparse("/api/sessions/session-1/git/changed_files")

        with patch.object(routes, "build_runtime_facade", return_value=facade):
            handled = routes.handle_get(object(), handler, u.path, u)

        self.assertTrue(handled)
        self.assertTrue(handler.unauthorized_called)
        self.assertEqual(facade.changed_files_calls, [])
        self.assertEqual(handler.responses, [])

    def test_git_diff_route_passes_query_args_to_facade(self) -> None:
        facade = _Facade()
        facade.diff_result = {"ok": True, "diff": "patch"}
        handler = _Handler()
        u = urllib.parse.urlparse("/api/sessions/session-2/git/diff?path=src%2Fapp.py&staged=1")

        with patch.object(routes, "build_runtime_facade", return_value=facade):
            handled = routes.handle_get(object(), handler, u.path, u)

        self.assertTrue(handled)
        self.assertEqual(facade.diff_calls, [("session-2", "src/app.py", True)])
        self.assertEqual(handler.responses, [(200, {"ok": True, "diff": "patch"})])

    def test_git_diff_route_rejects_missing_path(self) -> None:
        facade = _Facade()
        handler = _Handler()
        u = urllib.parse.urlparse("/api/sessions/session-3/git/diff")

        with patch.object(routes, "build_runtime_facade", return_value=facade):
            handled = routes.handle_get(object(), handler, u.path, u)

        self.assertTrue(handled)
        self.assertEqual(facade.diff_calls, [])
        self.assertEqual(handler.responses, [(400, {"error": "path required"})])

    def test_git_diff_route_maps_unknown_session_to_404(self) -> None:
        facade = _Facade()
        facade.diff_result = KeyError("unknown session")
        handler = _Handler()
        u = urllib.parse.urlparse("/api/sessions/session-3/git/diff?path=src%2Fapp.py")

        with patch.object(routes, "build_runtime_facade", return_value=facade):
            handled = routes.handle_get(object(), handler, u.path, u)

        self.assertTrue(handled)
        self.assertEqual(facade.diff_calls, [("session-3", "src/app.py", False)])
        self.assertEqual(handler.responses, [(404, {"error": "unknown session"})])

    def test_git_file_versions_route_maps_value_error_to_400(self) -> None:
        facade = _Facade()
        facade.file_versions_result = ValueError("outside repo")
        handler = _Handler()
        u = urllib.parse.urlparse("/api/sessions/session-4/git/file_versions?path=../secret.txt")

        with patch.object(routes, "build_runtime_facade", return_value=facade):
            handled = routes.handle_get(object(), handler, u.path, u)

        self.assertTrue(handled)
        self.assertEqual(facade.file_versions_calls, [("session-4", "../secret.txt")])
        self.assertEqual(handler.responses, [(400, {"error": "outside repo"})])

    def test_git_file_versions_route_rejects_missing_session_id(self) -> None:
        facade = _Facade()
        handler = _Handler()
        u = urllib.parse.urlparse("/api/sessions//git/file_versions?path=tracked.py")

        with patch.object(routes, "build_runtime_facade", return_value=facade):
            handled = routes.handle_get(object(), handler, u.path, u)

        self.assertTrue(handled)
        self.assertEqual(handler.sent_error, 404)
        self.assertEqual(facade.file_versions_calls, [])

    def test_changed_files_route_maps_runtime_error_to_409(self) -> None:
        facade = _Facade()
        facade.changed_files_result = RuntimeError("not a git repo")
        handler = _Handler()
        u = urllib.parse.urlparse("/api/sessions/session-5/git/changed_files")

        with patch.object(routes, "build_runtime_facade", return_value=facade):
            handled = routes.handle_get(object(), handler, u.path, u)

        self.assertTrue(handled)
        self.assertEqual(handler.responses, [(409, {"error": "not a git repo"})])


if __name__ == "__main__":
    unittest.main()
