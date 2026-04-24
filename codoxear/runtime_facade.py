from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime import ServerRuntime
from .runtime_facade_sessions import RuntimeFacadeSessionMixin
from .runtime_facade_voice import RuntimeFacadeVoiceMixin


class FacadeRequestError(ValueError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


@dataclass(slots=True)
class RuntimeFacade(RuntimeFacadeSessionMixin, RuntimeFacadeVoiceMixin):
    runtime: ServerRuntime

    @property
    def api(self) -> Any:
        return self.runtime.api

    @property
    def manager(self) -> Any:
        return self.runtime.manager

    def require_auth(self, handler: Any) -> bool:
        return bool(self.api.require_auth(handler))

    def json_response(self, handler: Any, status: int, payload: dict[str, Any]) -> None:
        self.api.json_response(handler, status, payload)

    def read_body(self, handler: Any, *, limit: int | None = None) -> bytes:
        if limit is None:
            return self.api.read_body(handler)
        return self.api.read_body(handler, limit=limit)

    def is_same_password(self, password: str) -> bool:
        return bool(self.api.is_same_password(password))

    def set_auth_cookie(self, handler: Any) -> None:
        self.api.set_auth_cookie(handler)

    def logout_cookie_header(self) -> str:
        return (
            f"{self.api.COOKIE_NAME}=deleted; Path={self.api.COOKIE_PATH}; "
            "Max-Age=0; HttpOnly; SameSite=Strict"
        )

    def resolve_public_web_asset(self, asset: str) -> Path | None:
        return self.api.resolve_public_web_asset(asset)

    def read_web_index(self) -> tuple[str, str]:
        return self.api.read_web_index()

    def use_legacy_web(self) -> bool:
        return bool(self.api.USE_LEGACY_WEB)

    def served_web_dist_dir(self) -> Path | None:
        return self.api.served_web_dist_dir()

    def is_path_within(self, root: Path, candidate: Path) -> bool:
        return bool(self.api.is_path_within(root, candidate))

    def file_kind(self, path_obj: Path, raw: bytes) -> tuple[str, str | None]:
        return self.api.file_kind(path_obj, raw)

    def file_search_limit(self) -> int:
        return int(self.api.FILE_SEARCH_LIMIT)

    def file_read_max_bytes(self) -> int:
        return int(self.api.FILE_READ_MAX_BYTES)

    def attach_upload_body_max_bytes(self) -> int:
        return int(self.api.ATTACH_UPLOAD_BODY_MAX_BYTES)

    def attach_upload_max_bytes(self) -> int:
        return int(self.api.ATTACH_UPLOAD_MAX_BYTES)

    def workspace_download_disposition(self, path_obj: Path) -> str:
        return self.api.workspace_file_access.download_disposition(path_obj)

    def workspace_read_text_file_for_write(self, path_obj: Path) -> tuple[str, int, str]:
        return self.api.workspace_file_access.read_text_file_for_write(
            path_obj,
            max_bytes=self.api.FILE_READ_MAX_BYTES,
        )

    def match_session_route(self, path: str, *suffix: str) -> str | None:
        return self.api.match_session_route(path, *suffix)

    def poll_events(self, after_seq: int, *, timeout_s: float) -> Any:
        return self.api.EVENT_HUB.poll(after_seq, timeout_s=timeout_s)



def build_runtime_facade(runtime: ServerRuntime) -> RuntimeFacade:
    return RuntimeFacade(runtime)
