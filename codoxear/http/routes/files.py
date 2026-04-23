from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any

from ...runtime import ServerRuntime
from ...workspace import service as _workspace_service


def _send_inline_blob(runtime: ServerRuntime, handler: Any, path_obj: Path) -> None:
    sv = runtime
    raw = path_obj.read_bytes()
    kind, ctype = sv._file_kind(path_obj, raw)
    if kind not in {"image", "pdf"} or ctype is None:
        sv._json_response(handler, 400, {"error": "file is not previewable inline"})
        return
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header(
        "Content-Disposition",
        f"inline; filename*=UTF-8''{urllib.parse.quote(path_obj.name, safe='')}",
    )
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Expires", "0")
    handler.end_headers()
    handler.wfile.write(raw)


def _read_json_object(runtime: ServerRuntime, handler: Any, *, limit: int | None = None) -> dict[str, Any]:
    body = runtime._read_body(handler, limit=limit or 2 * 1024 * 1024)
    body_text = body.decode("utf-8")
    if not body_text.strip():
        raise ValueError("empty request body")
    obj = json.loads(body_text)
    if not isinstance(obj, dict):
        raise ValueError("invalid json body (expected object)")
    return obj


def _session_id_from_path(path: str) -> str:
    parts = path.split("/")
    return parts[3] if len(parts) >= 4 else ""


def _require_query_value(runtime: ServerRuntime, handler: Any, query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values or not values[0]:
        runtime._json_response(handler, 400, {"error": f"{key} required"})
        return None
    return values[0]


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    sv = runtime
    if path.startswith("/api/sessions/") and path.endswith("/file/read"):
        if not sv._require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        rel = _require_query_value(sv, handler, urllib.parse.parse_qs(u.query), "path")
        if rel is None:
            return True
        try:
            payload = _workspace_service.read_session_file(runtime, session_id, rel)
        except KeyError:
            sv._json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            sv._json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            sv._json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            sv._json_response(handler, 400, {"error": str(exc)})
            return True
        sv._json_response(handler, 200, payload)
        return True
    if path.startswith("/api/sessions/") and path.endswith("/file/search"):
        if not sv._require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        qs = urllib.parse.parse_qs(u.query)
        query = (qs.get("q") or [""])[0].strip()
        if not query:
            sv._json_response(handler, 400, {"error": "q required"})
            return True
        limit_raw = (qs.get("limit") or [str(sv.FILE_SEARCH_LIMIT)])[0]
        try:
            limit = int(str(limit_raw).strip() or str(sv.FILE_SEARCH_LIMIT))
        except ValueError:
            sv._json_response(handler, 400, {"error": "limit must be an integer"})
            return True
        if limit < 1:
            sv._json_response(handler, 400, {"error": "limit must be >= 1"})
            return True
        try:
            payload = _workspace_service.search_session_files(runtime, session_id, query, limit)
        except KeyError:
            sv._json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            sv._json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            sv._json_response(handler, 403, {"error": str(exc)})
            return True
        except (RuntimeError, ValueError) as exc:
            sv._json_response(handler, 400, {"error": str(exc)})
            return True
        sv._json_response(handler, 200, payload)
        return True
    if path.startswith("/api/sessions/") and path.endswith("/file/list"):
        if not sv._require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        raw_rel = (urllib.parse.parse_qs(u.query).get("path") or [""])[0]
        try:
            payload = _workspace_service.list_session_files(runtime, session_id, raw_rel)
        except KeyError:
            sv._json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            sv._json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            sv._json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            sv._json_response(handler, 400, {"error": str(exc)})
            return True
        sv._json_response(handler, 200, payload)
        return True
    if path.startswith("/api/sessions/") and path.endswith("/file/blob"):
        if not sv._require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        rel = _require_query_value(sv, handler, urllib.parse.parse_qs(u.query), "path")
        if rel is None:
            return True
        try:
            path_obj = _workspace_service.resolve_session_blob(runtime, session_id, rel)
        except KeyError:
            sv._json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            sv._json_response(handler, 404, {"error": str(exc)})
            return True
        except ValueError as exc:
            sv._json_response(handler, 400, {"error": str(exc)})
            return True
        _send_inline_blob(runtime, handler, path_obj)
        return True
    if path == "/api/files/blob":
        if not sv._require_auth(handler):
            handler._unauthorized()
            return True
        raw_path = _require_query_value(sv, handler, urllib.parse.parse_qs(u.query), "path")
        if raw_path is None:
            return True
        try:
            path_obj = _workspace_service.resolve_client_blob(runtime, raw_path)
        except FileNotFoundError as exc:
            sv._json_response(handler, 404, {"error": str(exc)})
            return True
        except ValueError as exc:
            sv._json_response(handler, 400, {"error": str(exc)})
            return True
        _send_inline_blob(runtime, handler, path_obj)
        return True
    if path.startswith("/api/sessions/") and path.endswith("/file/download"):
        if not sv._require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _session_id_from_path(path)
        if not session_id:
            handler.send_error(404)
            return True
        rel = _require_query_value(sv, handler, urllib.parse.parse_qs(u.query), "path")
        if rel is None:
            return True
        try:
            path_obj, raw, size = _workspace_service.download_session_file(runtime, session_id, rel)
        except KeyError:
            sv._json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileNotFoundError as exc:
            sv._json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            sv._json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            sv._json_response(handler, 400, {"error": str(exc)})
            return True
        handler.send_response(200)
        handler.send_header("Content-Type", "application/octet-stream")
        handler.send_header("Content-Length", str(size))
        handler.send_header(
            "Content-Disposition",
            sv._workspace_file_access.download_disposition(path_obj),
        )
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Pragma", "no-cache")
        handler.send_header("Expires", "0")
        handler.end_headers()
        handler.wfile.write(raw)
        return True
    return False


def handle_post(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    sv = runtime
    if path == "/api/files/read":
        if not sv._require_auth(handler):
            handler._unauthorized()
            return True
        obj = _read_json_object(sv, handler)
        path_raw = obj.get("path")
        if not isinstance(path_raw, str) or not path_raw.strip():
            sv._json_response(handler, 400, {"error": "path required"})
            return True
        session_id_raw = obj.get("session_id")
        session_id = session_id_raw if isinstance(session_id_raw, str) and session_id_raw else ""
        try:
            payload = _workspace_service.read_client_file(runtime, path_raw, session_id)
        except FileNotFoundError as exc:
            sv._json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            sv._json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            sv._json_response(handler, 400, {"error": str(exc)})
            return True
        sv._json_response(handler, 200, payload)
        return True
    if path == "/api/files/inspect":
        if not sv._require_auth(handler):
            handler._unauthorized()
            return True
        obj = _read_json_object(sv, handler)
        path_raw = obj.get("path")
        if not isinstance(path_raw, str) or not path_raw.strip():
            sv._json_response(handler, 400, {"error": "path required"})
            return True
        session_id_raw = obj.get("session_id")
        session_id = session_id_raw if isinstance(session_id_raw, str) and session_id_raw else ""
        try:
            payload = _workspace_service.inspect_client_file(runtime, path_raw, session_id)
        except FileNotFoundError as exc:
            sv._json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            sv._json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            sv._json_response(handler, 400, {"error": str(exc)})
            return True
        sv._json_response(handler, 200, payload)
        return True
    if path == "/api/files/blob":
        if not sv._require_auth(handler):
            handler._unauthorized()
            return True
        raw_path = _require_query_value(sv, handler, urllib.parse.parse_qs(u.query), "path")
        if raw_path is None:
            return True
        try:
            path_obj = _workspace_service.resolve_client_blob(runtime, raw_path)
        except FileNotFoundError as exc:
            sv._json_response(handler, 404, {"error": str(exc)})
            return True
        except ValueError as exc:
            sv._json_response(handler, 400, {"error": str(exc)})
            return True
        _send_inline_blob(runtime, handler, path_obj)
        return True
    session_id = sv._match_session_route(path, "file", "write")
    if session_id is not None:
        if not sv._require_auth(handler):
            handler._unauthorized()
            return True
        obj = _read_json_object(sv, handler)
        path_raw = obj.get("path")
        if not isinstance(path_raw, str) or not path_raw.strip():
            sv._json_response(handler, 400, {"error": "path required"})
            return True
        text_raw = obj.get("text")
        if not isinstance(text_raw, str):
            sv._json_response(handler, 400, {"error": "text must be a string"})
            return True
        create_raw = obj.get("create")
        create = create_raw if isinstance(create_raw, bool) else False
        version_raw = obj.get("version")
        if not create and (not isinstance(version_raw, str) or not version_raw.strip()):
            sv._json_response(handler, 400, {"error": "version required"})
            return True
        try:
            payload = _workspace_service.write_session_file(
                runtime,
                session_id,
                path_raw=path_raw,
                text=text_raw,
                create=create,
                version=version_raw if isinstance(version_raw, str) else None,
            )
        except KeyError:
            sv._json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileExistsError as exc:
            if create:
                path_obj = Path(str(exc.args[0] if exc.args else path_raw))
                payload = {"error": "file already exists", "conflict": True, "path": str(path_obj)}
                if path_obj.is_file():
                    try:
                        _current_text, _current_size, current_version = sv._read_text_file_for_write(
                            path_obj, max_bytes=sv.FILE_READ_MAX_BYTES
                        )
                        payload["version"] = current_version
                    except (FileNotFoundError, PermissionError, ValueError):
                        pass
            else:
                payload = {
                    "error": "file changed on disk",
                    "conflict": True,
                    "path": str(exc.args[0] if exc.args else path_raw),
                }
                if len(exc.args) > 1 and isinstance(exc.args[1], str) and exc.args[1].strip():
                    payload["version"] = exc.args[1]
            sv._json_response(handler, 409, payload)
            return True
        except FileNotFoundError as exc:
            sv._json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            sv._json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            sv._json_response(handler, 400, {"error": str(exc)})
            return True
        sv._json_response(handler, 200, payload)
        return True
    if path.startswith("/api/sessions/") and (path.endswith("/inject_file") or path.endswith("/inject_image")):
        if not sv._require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _session_id_from_path(path)
        try:
            obj = _read_json_object(sv, handler, limit=sv.ATTACH_UPLOAD_BODY_MAX_BYTES)
        except ValueError as exc:
            if "content-length" in str(exc):
                sv._json_response(handler, 413, {"error": f"file too large (max {sv.ATTACH_UPLOAD_MAX_BYTES} bytes)"})
                return True
            raise
        filename = obj.get("filename")
        attachment_index = obj.get("attachment_index")
        data_b64 = obj.get("data_b64")
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("filename required")
        if isinstance(attachment_index, bool) or not isinstance(attachment_index, int):
            sv._json_response(handler, 400, {"error": "attachment_index must be an integer"})
            return True
        if not isinstance(data_b64, str) or not data_b64:
            sv._json_response(handler, 400, {"error": "data_b64 required"})
            return True
        try:
            payload = _workspace_service.inject_session_attachment(
                runtime,
                session_id,
                filename=filename,
                attachment_index=attachment_index,
                data_b64=data_b64,
            )
        except KeyError:
            sv._json_response(handler, 404, {"error": "unknown session"})
            return True
        except RuntimeError as exc:
            if str(exc) == "pi-attachment-injection":
                sv._json_response(handler, 409, {
                    "error": "attachment injection is not supported for Pi sessions",
                    "backend": "pi",
                    "operation": "attachment_injection",
                })
                return True
            raise
        except ConnectionError as exc:
            sv._json_response(handler, 502, {"error": str(exc)})
            return True
        except ValueError as exc:
            status = 413 if str(exc).startswith("file too large") else 400
            sv._json_response(handler, status, {"error": str(exc)})
            return True
        sv._json_response(handler, 200, payload)
        return True
    return False
