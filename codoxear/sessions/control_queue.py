from __future__ import annotations

from pathlib import Path
from typing import Any

from . import historical_resume as _historical_resume


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def send(manager: Any, session_id: str, text: str) -> dict[str, Any]:
    resumed = _historical_resume.resume_historical_pi_session(manager, session_id)
    if resumed is not None:
        resp = send(manager, resumed["runtime_id"], text)
        out = dict(resp)
        out["session_id"] = resumed["session_id"]
        out["runtime_id"] = resumed["runtime_id"]
        out["backend"] = resumed["backend"]
        return out

    runtime_id = manager._runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        raise KeyError("unknown session")
    with manager._lock:
        session = manager._sessions.get(runtime_id)
        if not session:
            raise KeyError("unknown session")
        durable_session_id = manager._durable_session_id_for_session(session)
    transport_state, transport_error = manager._probe_bridge_transport(runtime_id)
    if transport_state == "dead":
        with manager._lock:
            manager._sessions.pop(runtime_id, None)
        manager._clear_deleted_session_state(runtime_id)
        _unlink_quiet(session.sock_path)
        _unlink_quiet(session.sock_path.with_suffix(".json"))
        raise KeyError("unknown session")
    request = manager._enqueue_outbound_request(runtime_id, text)
    return {
        "ok": True,
        "accepted": True,
        "request_id": request.request_id,
        "delivery_state": request.state,
        "session_id": durable_session_id,
        "runtime_id": runtime_id,
        "backend": session.backend,
        "transport_state": transport_state,
        "transport_error": transport_error,
    }


def enqueue(manager: Any, session_id: str, text: str) -> dict[str, Any]:
    resumed = _historical_resume.resume_historical_pi_session(manager, session_id)
    if resumed is not None:
        resp = enqueue(manager, resumed["runtime_id"], text)
        out = dict(resp)
        out["session_id"] = resumed["session_id"]
        out["runtime_id"] = resumed["runtime_id"]
        out["backend"] = resumed["backend"]
        return out
    return manager._queue_enqueue_local(session_id, text)


def queue_list(manager: Any, session_id: str) -> list[str]:
    runtime_id = manager._runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        raise KeyError("unknown session")
    return manager._queue_list_local(runtime_id)


def queue_delete(manager: Any, session_id: str, index: int) -> dict[str, Any]:
    return manager._queue_delete_local(session_id, int(index))


def queue_update(manager: Any, session_id: str, index: int, text: str) -> dict[str, Any]:
    return manager._queue_update_local(session_id, int(index), text)
