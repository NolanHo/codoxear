from __future__ import annotations

from pathlib import Path
from typing import Any
import urllib.parse

from ...runtime import ServerRuntime
from ...workspace import service as _workspace_service
from . import files_common as _common


def handle_post(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    if path == "/api/files/read":
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _common.read_json_object(runtime, handler)
        path_raw = obj.get("path")
        if not isinstance(path_raw, str) or not path_raw.strip():
            runtime.api.json_response(handler, 400, {"error": "path required"})
            return True
        session_id_raw = obj.get("session_id")
        session_id = session_id_raw if isinstance(session_id_raw, str) and session_id_raw else ""
        try:
            payload = _workspace_service.read_client_file(runtime, path_raw, session_id)
        except FileNotFoundError as exc:
            runtime.api.json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            runtime.api.json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 400, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, payload)
        return True

    if path == "/api/files/inspect":
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _common.read_json_object(runtime, handler)
        path_raw = obj.get("path")
        if not isinstance(path_raw, str) or not path_raw.strip():
            runtime.api.json_response(handler, 400, {"error": "path required"})
            return True
        session_id_raw = obj.get("session_id")
        session_id = session_id_raw if isinstance(session_id_raw, str) and session_id_raw else ""
        try:
            payload = _workspace_service.inspect_client_file(runtime, path_raw, session_id)
        except FileNotFoundError as exc:
            runtime.api.json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            runtime.api.json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 400, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, payload)
        return True

    if path == "/api/files/blob":
        if not runtime.api.require_auth(handler):
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
            runtime.api.json_response(handler, 404, {"error": str(exc)})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 400, {"error": str(exc)})
            return True
        _common.send_inline_blob(runtime, handler, path_obj)
        return True

    session_id = runtime.api.match_session_route(path, "file", "write")
    if session_id is not None:
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _common.read_json_object(runtime, handler)
        path_raw = obj.get("path")
        if not isinstance(path_raw, str) or not path_raw.strip():
            runtime.api.json_response(handler, 400, {"error": "path required"})
            return True
        text_raw = obj.get("text")
        if not isinstance(text_raw, str):
            runtime.api.json_response(handler, 400, {"error": "text must be a string"})
            return True
        create_raw = obj.get("create")
        create = create_raw if isinstance(create_raw, bool) else False
        version_raw = obj.get("version")
        if not create and (not isinstance(version_raw, str) or not version_raw.strip()):
            runtime.api.json_response(handler, 400, {"error": "version required"})
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
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except FileExistsError as exc:
            if create:
                path_obj = Path(str(exc.args[0] if exc.args else path_raw))
                payload = {
                    "error": "file already exists",
                    "conflict": True,
                    "path": str(path_obj),
                }
                if path_obj.is_file():
                    try:
                        _current_text, _current_size, current_version = runtime.api.workspace_file_access.read_text_file_for_write(
                            path_obj,
                            max_bytes=runtime.api.FILE_READ_MAX_BYTES,
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
            runtime.api.json_response(handler, 409, payload)
            return True
        except FileNotFoundError as exc:
            runtime.api.json_response(handler, 404, {"error": str(exc)})
            return True
        except PermissionError as exc:
            runtime.api.json_response(handler, 403, {"error": str(exc)})
            return True
        except ValueError as exc:
            runtime.api.json_response(handler, 400, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, payload)
        return True

    if path.startswith("/api/sessions/") and (path.endswith("/inject_file") or path.endswith("/inject_image")):
        if not runtime.api.require_auth(handler):
            handler._unauthorized()
            return True
        session_id = _common.session_id_from_path(path)
        try:
            obj = _common.read_json_object(
                runtime,
                handler,
                limit=runtime.api.ATTACH_UPLOAD_BODY_MAX_BYTES,
            )
        except ValueError as exc:
            if "content-length" in str(exc):
                runtime.api.json_response(
                    handler,
                    413,
                    {"error": f"file too large (max {runtime.api.ATTACH_UPLOAD_MAX_BYTES} bytes)"},
                )
                return True
            raise
        filename = obj.get("filename")
        attachment_index = obj.get("attachment_index")
        data_b64 = obj.get("data_b64")
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("filename required")
        if isinstance(attachment_index, bool) or not isinstance(attachment_index, int):
            runtime.api.json_response(handler, 400, {"error": "attachment_index must be an integer"})
            return True
        if not isinstance(data_b64, str) or not data_b64:
            runtime.api.json_response(handler, 400, {"error": "data_b64 required"})
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
            runtime.api.json_response(handler, 404, {"error": "unknown session"})
            return True
        except RuntimeError as exc:
            if str(exc) == "pi-attachment-injection":
                runtime.api.json_response(
                    handler,
                    409,
                    {
                        "error": "attachment injection is not supported for Pi sessions",
                        "backend": "pi",
                        "operation": "attachment_injection",
                    },
                )
                return True
            raise
        except ConnectionError as exc:
            runtime.api.json_response(handler, 502, {"error": str(exc)})
            return True
        except ValueError as exc:
            status = 413 if str(exc).startswith("file too large") else 400
            runtime.api.json_response(handler, status, {"error": str(exc)})
            return True
        runtime.api.json_response(handler, 200, payload)
        return True

    return False
