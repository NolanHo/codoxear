from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..page_state_sqlite import SessionRef
from . import catalog_discovery as _catalog_discovery
from . import catalog_identity as _catalog_identity
from . import catalog_listing as _catalog_listing
from . import catalog_meta as _catalog_meta
from . import catalog_state as _catalog_state



@dataclass(slots=True)
class SessionCatalogService:
    manager: Any

    def listed_session_row(self, session_id: str) -> dict[str, Any] | None:
        return listed_session_row(self.manager, session_id)

    def runtime_session_id_for_identifier(self, session_id: str) -> str | None:
        return runtime_session_id_for_identifier(self.manager, session_id)

    def durable_session_id_for_identifier(self, session_id: str) -> str | None:
        return durable_session_id_for_identifier(self.manager, session_id)

    def page_state_ref_for_session_id(self, session_id: str) -> SessionRef | None:
        return page_state_ref_for_session_id(self.manager, session_id)

    def discover_existing(
        self, *, force: bool = False, skip_invalid_sidecars: bool = False
    ) -> None:
        discover_existing(
            self.manager,
            force=force,
            skip_invalid_sidecars=skip_invalid_sidecars,
        )

    def refresh_session_state(
        self, session_id: str, sock_path: Path, timeout_s: float = 0.4
    ) -> tuple[bool, BaseException | None]:
        return refresh_session_state(
            self.manager,
            session_id,
            sock_path,
            timeout_s=timeout_s,
        )

    def prune_dead_sessions(self) -> None:
        prune_dead_sessions(self.manager)

    def list_sessions(self) -> list[dict[str, Any]]:
        return list_sessions(self.manager)

    def get_session(self, session_id: str) -> Any | None:
        return get_session(self.manager, session_id)

    def refresh_session_meta(self, session_id: str, *, strict: bool = True) -> None:
        refresh_session_meta(self.manager, session_id, strict=strict)


def service(manager: Any) -> SessionCatalogService:
    return SessionCatalogService(manager)


def runtime_session_id_for_identifier(manager: Any, session_id: str) -> str | None:
    return _catalog_identity.runtime_session_id_for_identifier(manager, session_id)


def durable_session_id_for_identifier(manager: Any, session_id: str) -> str | None:
    return _catalog_identity.durable_session_id_for_identifier(manager, session_id)


def page_state_ref_for_session_id(manager: Any, session_id: str) -> SessionRef | None:
    return _catalog_identity.page_state_ref_for_session_id(manager, session_id)


def get_session(manager: Any, session_id: str) -> Any | None:
    return _catalog_identity.get_session(manager, session_id)


def listed_session_row(manager: Any, session_id: str) -> dict[str, Any] | None:
    return _catalog_identity.listed_session_row(manager, session_id)


def refresh_session_meta(manager: Any, session_id: str, *, strict: bool = True) -> None:
    _catalog_meta.refresh_session_meta(manager, session_id, strict=strict)


def list_sessions(manager: Any) -> list[dict[str, Any]]:
    return _catalog_listing.list_sessions(manager)


def discover_existing(
    manager: Any, *, force: bool = False, skip_invalid_sidecars: bool = False
) -> None:
    _catalog_discovery.discover_existing(
        manager,
        force=force,
        skip_invalid_sidecars=skip_invalid_sidecars,
    )


def refresh_session_state(
    manager: Any, session_id: str, sock_path: Path, timeout_s: float = 0.4
) -> tuple[bool, BaseException | None]:
    return _catalog_state.refresh_session_state(
        manager,
        session_id,
        sock_path,
        timeout_s=timeout_s,
    )


def prune_dead_sessions(manager: Any) -> None:
    _catalog_state.prune_dead_sessions(manager)
