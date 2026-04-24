from __future__ import annotations

import urllib.parse
from typing import Any

from ...runtime import ServerRuntime
from ...runtime_facade import build_runtime_facade
from ...workspace import service as _workspace_service
from . import files_common as _common


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    facade = build_runtime_facade(runtime)

    if path.startswith("/api/sessions/") and path.endswith("/file/read"):
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        rel = _common.require_query_value(
            facade,
            handler,
            urllib.parse.parse_qs(u.query),
            "path",
        )
        if rel is None:
            return True
        try:
            payload = _workspace_service.read_session_file(runtime, session_id, rel)
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            facade.json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            facade.json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/file/search"):
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        qs = urllib.parse.parse_qs(u.query)
        query = (qs.get("q") or [""])[0].strip()
        if not query:
            facade.json_response(handler, 400, {"error": "q required"})
            return True
        limit_raw = (qs.get("limit") or [str(facade.file_search_limit())])[0]
        try:
            limit = int(str(limit_raw).strip() or str(facade.file_search_limit()))
        except ValueError:
            facade.json_response(handler, 400, {"error": "limit must be an integer"})
            return True
        if limit < 1:
            facade.json_response(handler, 400, {"error": "limit must be >= 1"})
            return True
        try:
            payload = _workspace_service.search_session_files(runtime, session_id, query, limit)
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            facade.json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            facade.json_response(handler, 403, {"error": str(exc)})
            return True
        except (RuntimeError, ValueError) as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/file/list"):
        if not facade.require_auth(handler):
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
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            facade.json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            facade.json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/file/blob"):
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        rel = _common.require_query_value(
            facade,
            handler,
            urllib.parse.parse_qs(u.query),
            "path",
        )
        if rel is None:
            return True
        try:
            path_obj = _workspace_service.resolve_session_blob(runtime, session_id, rel)
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            facade.json_response(handler, 404, {"error": str(exc)})
            return True
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        _common.send_inline_blob(facade, handler, path_obj)
        return True

    if path == "/api/files/blob":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        raw_path = _common.require_query_value(
            facade,
            handler,
            urllib.parse.parse_qs(u.query),
            "path",
        )
        if raw_path is None:
            return True
        try:
            path_obj = _workspace_service.resolve_client_blob(runtime, raw_path)
        except FileNotFoundError as exc:
            facade.json_response(handler, 404, {"error": str(exc)})
            return True
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        _common.send_inline_blob(facade, handler, path_obj)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/file/download"):
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        rel = _common.require_query_value(
            facade,
            handler,
            urllib.parse.parse_qs(u.query),
            "path",
        )
        if rel is None:
            return True
        try:
            path_obj, raw, size = _workspace_service.download_session_file(runtime, session_id, rel)
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            facade.json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            facade.json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            facade.json_response(handler, 400, {"error": str(exc)})
            return True
        handler.send_response(200)
        handler.send_header("Content-Type", "application/octet-stream")
        handler.send_header("Content-Length", str(size))
        handler.send_header(
            "Content-Disposition",
            facade.workspace_download_disposition(path_obj),
        )
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Pragma", "no-cache")
        handler.send_header("Expires", "0")
        handler.end_headers()
        handler.wfile.write(raw)
        return True

    return False
