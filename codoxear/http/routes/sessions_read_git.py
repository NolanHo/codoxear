from __future__ import annotations

import urllib.parse
from typing import Any

from ...runtime import ServerRuntime
from ...runtime_facade import build_runtime_facade
from . import sessions_read_common as _common


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    facade = build_runtime_facade(runtime)

    if path.startswith("/api/sessions/") and path.endswith("/git/changed_files"):
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        try:
            payload = facade.session_git_changed_files_payload(session_id)
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        except RuntimeError as exc:
            facade.json_response(handler, 409, {"error": str(exc)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/git/diff"):
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        qs = urllib.parse.parse_qs(u.query)
        path_q = qs.get("path")
        if not path_q or not path_q[0]:
            facade.json_response(handler, 400, {"error": "path required"})
            return True
        rel = path_q[0]
        staged_q = qs.get("staged")
        staged = bool(staged_q and staged_q[0] == "1")
        try:
            payload = facade.session_git_diff_payload(
                session_id,
                rel_path=rel,
                staged=staged,
            )
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        except RuntimeError as exc:
            facade.json_response(handler, 409, {"error": str(exc)})
            return True
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/git/file_versions"):
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        qs = urllib.parse.parse_qs(u.query)
        path_q = qs.get("path")
        if not path_q or not path_q[0]:
            facade.json_response(handler, 400, {"error": "path required"})
            return True
        rel = path_q[0]
        try:
            payload = facade.session_git_file_versions_payload(
                session_id,
                rel_path=rel,
            )
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        except RuntimeError as exc:
            facade.json_response(handler, 409, {"error": str(exc)})
            return True
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    return False
