from __future__ import annotations

import urllib.parse
from typing import Any

from ...runtime import ServerRuntime
from ...workspace import service as _workspace_service
from . import files_common as _common


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    if path.startswith("/api/sessions/") and path.endswith("/file/read"):
        if not runtime._require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        rel = _common.require_query_value(
            runtime,
            handler,
            urllib.parse.parse_qs(u.query),
            "path",
        )
        if rel is None:
            return True
        try:
            payload = _workspace_service.read_session_file(runtime, session_id, rel)
        except KeyError:
            runtime._json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            runtime._json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            runtime._json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            runtime._json_response(handler, 400, {"error": str(exc)})
            return True
        runtime._json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/file/search"):
        if not runtime._require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        qs = urllib.parse.parse_qs(u.query)
        query = (qs.get("q") or [""])[0].strip()
        if not query:
            runtime._json_response(handler, 400, {"error": "q required"})
            return True
        limit_raw = (qs.get("limit") or [str(runtime.FILE_SEARCH_LIMIT)])[0]
        try:
            limit = int(str(limit_raw).strip() or str(runtime.FILE_SEARCH_LIMIT))
        except ValueError:
            runtime._json_response(handler, 400, {"error": "limit must be an integer"})
            return True
        if limit < 1:
            runtime._json_response(handler, 400, {"error": "limit must be >= 1"})
            return True
        try:
            payload = _workspace_service.search_session_files(runtime, session_id, query, limit)
        except KeyError:
            runtime._json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            runtime._json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            runtime._json_response(handler, 403, {"error": str(exc)})
            return True
        except (RuntimeError, ValueError) as exc:
            runtime._json_response(handler, 400, {"error": str(exc)})
            return True
        runtime._json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/file/list"):
        if not runtime._require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        raw_rel = (urllib.parse.parse_qs(u.query).get("path") or [""])[0]
        try:
            payload = _workspace_service.list_session_files(runtime, session_id, raw_rel)
        except KeyError:
            runtime._json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            runtime._json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            runtime._json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            runtime._json_response(handler, 400, {"error": str(exc)})
            return True
        runtime._json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/file/blob"):
        if not runtime._require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        rel = _common.require_query_value(
            runtime,
            handler,
            urllib.parse.parse_qs(u.query),
            "path",
        )
        if rel is None:
            return True
        try:
            path_obj = _workspace_service.resolve_session_blob(runtime, session_id, rel)
        except KeyError:
            runtime._json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            runtime._json_response(handler, 404, {"error": str(exc)})
            return True
        except ValueError as exc:
            runtime._json_response(handler, 400, {"error": str(exc)})
            return True
        _common.send_inline_blob(runtime, handler, path_obj)
        return True

    if path == "/api/files/blob":
        if not runtime._require_auth(handler):
            handler._unauthorized()
            return True
        raw_path = _common.require_query_value(
            runtime,
            handler,
            urllib.parse.parse_qs(u.query),
            "path",
        )
        if raw_path is None:
            return True
        try:
            path_obj = _workspace_service.resolve_client_blob(runtime, raw_path)
        except FileNotFoundError as exc:
            runtime._json_response(handler, 404, {"error": str(exc)})
            return True
        except ValueError as exc:
            runtime._json_response(handler, 400, {"error": str(exc)})
            return True
        _common.send_inline_blob(runtime, handler, path_obj)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/file/download"):
        if not runtime._require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        rel = _common.require_query_value(
            runtime,
            handler,
            urllib.parse.parse_qs(u.query),
            "path",
        )
        if rel is None:
            return True
        try:
            path_obj, raw, size = _workspace_service.download_session_file(runtime, session_id, rel)
        except KeyError:
            runtime._json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            runtime._json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            runtime._json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            runtime._json_response(handler, 400, {"error": str(exc)})
            return True
        handler.send_response(200)
        handler.send_header("Content-Type", "application/octet-stream")
        handler.send_header("Content-Length", str(size))
        handler.send_header(
            "Content-Disposition",
            runtime._workspace_file_access.download_disposition(path_obj),
        )
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Pragma", "no-cache")
        handler.send_header("Expires", "0")
        handler.end_headers()
        handler.wfile.write(raw)
        return True

    return False
