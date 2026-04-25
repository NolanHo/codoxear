from __future__ import annotations

import json
import socket
import traceback
from typing import TYPE_CHECKING, Any

from .util import _send_socket_json_line as _send_socket_json_line
from .util import _socket_peer_disconnected as _socket_peer_disconnected

if TYPE_CHECKING:
    from .pi_broker import PiBroker

_STATE_RESPONSE_KEYS = (
    "model",
    "thinkingLevel",
    "isStreaming",
    "sessionFile",
    "sessionId",
    "sessionName",
    "autoCompactionEnabled",
    "messageCount",
    "pendingMessageCount",
)


def _seq_bytes(raw: str) -> bytes:
    try:
        return raw.encode("utf-8").decode("unicode_escape").encode("utf-8")
    except Exception:
        return raw.encode("utf-8")


def _coalesce_live_message_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coalesced: list[dict[str, Any]] = []
    latest_open_index_by_stream: dict[str, int] = {}
    for row in rows:
        stream_id = (
            row.get("stream_id") if isinstance(row.get("stream_id"), str) else ""
        )
        completed = row.get("completed") is True
        if stream_id and not completed:
            existing_index = latest_open_index_by_stream.get(stream_id)
            if existing_index is not None:
                coalesced[existing_index] = row
            else:
                latest_open_index_by_stream[stream_id] = len(coalesced)
                coalesced.append(row)
            continue
        coalesced.append(row)
        if stream_id and completed:
            latest_open_index_by_stream.pop(stream_id, None)
    return coalesced


class PiBrokerSocketProtocol:
    """Unix-socket request/response layer for PiBroker."""

    def __init__(self, broker: PiBroker) -> None:
        self._broker = broker

    def handle_conn(self, conn: socket.socket) -> None:
        try:
            req = self._read_request(conn)
            if req is None:
                return
            cmd = req.get("cmd")
            if self._dispatch_command(conn, cmd, req):
                return
            _send_socket_json_line(conn, {"error": "unknown cmd"})
        except Exception as exc:
            self._send_error(conn, exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _read_request(self, conn: socket.socket) -> dict[str, Any] | None:
        f = conn.makefile("rb")
        try:
            line = f.readline()
            if not line:
                return None
            req = json.loads(line.decode("utf-8"))
            return req if isinstance(req, dict) else {"cmd": None}
        finally:
            try:
                f.close()
            except Exception:
                pass

    def _send_error(self, conn: socket.socket, exc: Exception) -> None:
        if _socket_peer_disconnected(exc):
            return
        try:
            error = str(exc).strip() or "exception"
            payload = {"error": error}
            if error == "exception":
                payload["trace"] = traceback.format_exc()
            _send_socket_json_line(conn, payload)
        except Exception:
            pass

    def _dispatch_command(
        self,
        conn: socket.socket,
        cmd: Any,
        req: dict[str, Any],
    ) -> bool:
        handlers = {
            "state": self._cmd_state,
            "session_stats": self._cmd_session_stats,
            "tail": self._cmd_tail,
            "live_messages": self._cmd_live_messages,
            "ui_state": self._cmd_ui_state,
            "commands": self._cmd_commands,
            "set_model": self._cmd_set_model,
            "ui_response": self._cmd_ui_response,
            "send": self._cmd_send,
            "keys": self._cmd_keys,
            "shutdown": self._cmd_shutdown,
        }
        handler = handlers.get(cmd)
        if handler is None:
            return False
        handler(conn, req)
        return True

    def _cmd_state(self, conn: socket.socket, _req: dict[str, Any]) -> None:
        broker = self._broker
        with broker._lock:
            st = broker.state
            if st is not None:
                broker._drain_rpc_output_locked(st)
            resp = {
                "busy": bool(st.busy) if st else False,
                "queue_len": 0,
                "token": st.token if st else None,
                "isCompacting": bool(st.is_compacting) if st else False,
            }
            native_state = st.rpc_state if st is not None else None
            if isinstance(native_state, dict):
                for key in _STATE_RESPONSE_KEYS:
                    if key in native_state:
                        resp[key] = native_state.get(key)
        _send_socket_json_line(conn, resp)

    def _cmd_session_stats(self, conn: socket.socket, _req: dict[str, Any]) -> None:
        broker = self._broker
        with broker._lock:
            st = broker.state
            if st is not None:
                broker._drain_rpc_output_locked(st)
            resp = (
                dict(st.session_stats)
                if st is not None and isinstance(st.session_stats, dict)
                else {}
            )
        _send_socket_json_line(conn, resp)

    def _cmd_tail(self, conn: socket.socket, _req: dict[str, Any]) -> None:
        broker = self._broker
        with broker._lock:
            st = broker.state
            if st is not None:
                broker._drain_rpc_output_locked(st)
            resp = {"tail": st.output_tail if st else ""}
        _send_socket_json_line(conn, resp)

    def _cmd_live_messages(self, conn: socket.socket, req: dict[str, Any]) -> None:
        raw_offset = req.get("offset")
        since_offset = int(raw_offset) if isinstance(raw_offset, int) else 0
        broker = self._broker
        with broker._lock:
            st = broker.state
            if st is not None:
                broker._drain_rpc_output_locked(st)
                events = [
                    dict(row.get("event", {}))
                    for row in st.live_message_events
                    if int(row.get("offset", 0)) > since_offset
                    and isinstance(row.get("event"), dict)
                ]
                resp = {
                    "offset": st.live_message_offset,
                    "events": _coalesce_live_message_events(events),
                }
            else:
                resp = {"offset": 0, "events": []}
        _send_socket_json_line(conn, resp)

    def _cmd_ui_state(self, conn: socket.socket, _req: dict[str, Any]) -> None:
        broker = self._broker
        with broker._lock:
            st = broker.state
            if st is not None:
                broker._drain_rpc_output_locked(st)
                requests = [
                    request
                    for request in st.pending_ui_requests.values()
                    if request.get("status") == "pending"
                ]
            else:
                requests = []
            resp = {"requests": requests}
        _send_socket_json_line(conn, resp)

    def _cmd_commands(self, conn: socket.socket, _req: dict[str, Any]) -> None:
        broker = self._broker
        with broker._lock:
            st = broker.state
            if st is not None:
                broker._drain_rpc_output_locked(st)
                rpc = st.rpc
            else:
                rpc = None
        if rpc is None:
            _send_socket_json_line(conn, {"error": "no state"})
            return
        _send_socket_json_line(conn, {"commands": rpc.get_commands()})

    def _cmd_set_model(self, conn: socket.socket, req: dict[str, Any]) -> None:
        model_raw = req.get("model")
        if model_raw is None:
            model_raw = req.get("model_id")
        if model_raw is None:
            model_raw = req.get("modelId")
        model_id = model_raw.strip() if isinstance(model_raw, str) else ""
        if not model_id:
            _send_socket_json_line(conn, {"error": "model required"})
            return
        provider_raw = req.get("provider")
        provider = provider_raw.strip() if isinstance(provider_raw, str) else None
        broker = self._broker
        with broker._lock:
            st = broker.state
            if st is not None:
                broker._drain_rpc_output_locked(st)
                rpc = st.rpc
            else:
                rpc = None
        if rpc is None:
            _send_socket_json_line(conn, {"error": "no state"})
            return
        data = rpc.set_model(model_id, provider=provider)
        _send_socket_json_line(conn, {"ok": True, "data": data})

    def _parse_ui_response_request(
        self,
        req: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        request_id = req.get("id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("id required")

        ui_response_kwargs: dict[str, Any] = {}
        if bool(req.get("cancelled")):
            ui_response_kwargs["cancelled"] = True
        else:
            confirmed = req.get("confirmed")
            if isinstance(confirmed, bool):
                ui_response_kwargs["confirmed"] = confirmed
            else:
                ui_response_kwargs["value"] = req.get("value")
        return request_id, ui_response_kwargs

    def _resolve_pending_ui_request(
        self,
        request_id: str,
    ) -> tuple[dict[str, Any], Any]:
        broker = self._broker
        with broker._lock:
            st = broker.state
            if not st:
                raise RuntimeError("no state")
            pending = st.pending_ui_requests.get(request_id)
            if pending is None:
                raise ValueError("unknown or expired request")
            if pending.get("status") != "pending":
                raise RuntimeError("request already resolved")
            pending["status"] = "resolved"
            rpc = st.rpc
        return pending, rpc

    def _restore_pending_ui_request_on_failure(
        self,
        *,
        request_id: str,
        expected_pending: dict[str, Any],
    ) -> None:
        broker = self._broker
        with broker._lock:
            st = broker.state
            current = st.pending_ui_requests.get(request_id) if st else None
            if (
                current is expected_pending
                and isinstance(current, dict)
                and current.get("status") == "resolved"
            ):
                current["status"] = "pending"

    def _cmd_ui_response(self, conn: socket.socket, req: dict[str, Any]) -> None:
        try:
            request_id, ui_response_kwargs = self._parse_ui_response_request(req)
        except ValueError as exc:
            _send_socket_json_line(conn, {"error": str(exc)})
            return

        try:
            pending, rpc = self._resolve_pending_ui_request(request_id)
        except (ValueError, RuntimeError) as exc:
            _send_socket_json_line(conn, {"error": str(exc)})
            return

        try:
            rpc.send_ui_response(request_id, **ui_response_kwargs)
        except Exception:
            self._restore_pending_ui_request_on_failure(
                request_id=request_id,
                expected_pending=pending,
            )
            raise

        _send_socket_json_line(conn, {"ok": True})

    def _cmd_send(self, conn: socket.socket, req: dict[str, Any]) -> None:
        text = req.get("text")
        if not isinstance(text, str) or not text.strip():
            _send_socket_json_line(conn, {"error": "text required"})
            return
        self._broker._submit_terminal_prompt(text)
        _send_socket_json_line(conn, {"queued": False, "queue_len": 0})

    def _cmd_keys(self, conn: socket.socket, req: dict[str, Any]) -> None:
        seq_raw = req.get("seq")
        if not isinstance(seq_raw, str) or not seq_raw:
            _send_socket_json_line(conn, {"error": "seq required"})
            return
        seq = _seq_bytes(seq_raw)
        broker = self._broker
        with broker._lock:
            st = broker.state
            if not st:
                _send_socket_json_line(conn, {"error": "no state"})
                return
        if seq != b"\x1b":
            _send_socket_json_line(conn, {"error": f"unsupported key sequence: {seq_raw}"})
            return
        broker._interrupt_terminal_turn()
        _send_socket_json_line(conn, {"ok": True, "queued": False, "n": len(seq)})

    def _cmd_shutdown(self, conn: socket.socket, _req: dict[str, Any]) -> None:
        _send_socket_json_line(conn, {"ok": True})
        self._broker._close()
