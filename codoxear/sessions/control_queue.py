from __future__ import annotations

from typing import Any

from . import historical_resume as _historical_resume


def send(manager: Any, session_id: str, text: str) -> dict[str, Any]:
    resumed = _historical_resume.resume_historical_pi_session(manager, session_id)
    if resumed is not None:
        resp = send(manager, resumed["runtime_id"], text)
        out = dict(resp)
        out["session_id"] = resumed["session_id"]
        out["runtime_id"] = resumed["runtime_id"]
        out["backend"] = resumed["backend"]
        return out

    runtime_id = manager.runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        raise KeyError("unknown session")
    session = manager.get_session(runtime_id)
    if session is None:
        raise KeyError("unknown session")
    durable_session_id = manager.durable_session_id_for_session(session)
    transport_state, transport_error = manager.probe_bridge_transport(runtime_id)
    if transport_state == "dead":
        manager.discard_runtime_session(runtime_id, sock_path=session.sock_path)
        raise KeyError("unknown session")
    request = manager.enqueue_outbound_request(runtime_id, text)
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
    return manager.queue_enqueue_local(session_id, text)


def queue_list(manager: Any, session_id: str) -> list[str]:
    runtime_id = manager.runtime_session_id_for_identifier(session_id)
    if runtime_id is None:
        raise KeyError("unknown session")
    return manager.queue_list_local(runtime_id)


def queue_delete(manager: Any, session_id: str, index: int) -> dict[str, Any]:
    return manager.queue_delete_local(session_id, int(index))


def queue_update(manager: Any, session_id: str, index: int, text: str) -> dict[str, Any]:
    return manager.queue_update_local(session_id, int(index), text)
