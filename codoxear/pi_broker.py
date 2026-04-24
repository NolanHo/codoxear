#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import tempfile
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .pi_log import pi_token_update as _pi_token_update
from .pi_rpc import PiRpcClient
from .util import _send_socket_json_line as _send_socket_json_line
from .util import _socket_peer_disconnected as _socket_peer_disconnected
from .util import default_app_dir as _default_app_dir

APP_DIR = _default_app_dir()
SOCK_DIR = APP_DIR / "socks"
PI_SESSION_DIR = APP_DIR / "pi-sessions"
OWNER_TAG = os.environ.get("CODEX_WEB_OWNER", "")

_TERMINAL_TURN_EVENT_TYPES = {
    "thread_rolled_back",
    "turn_end",
    "turn.aborted",
    "turn.completed",
    "turn.failed",
}

_DIALOG_UI_METHODS = {"select", "confirm", "input", "editor"}


def _seq_bytes(raw: str) -> bytes:
    try:
        return raw.encode("utf-8").decode("unicode_escape").encode("utf-8")
    except Exception:
        return raw.encode("utf-8")


def _extract_turn_id(obj: dict[str, Any]) -> str | None:
    for key in ("turn_id", "current_turn_id", "active_turn_id"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            return value
    payload = obj.get("payload")
    if isinstance(payload, dict):
        return _extract_turn_id(payload)
    return None


def _extract_session_id(obj: dict[str, Any]) -> str | None:
    for key in ("session_id", "sessionId"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            return value
    payload = obj.get("payload")
    if isinstance(payload, dict):
        return _extract_session_id(payload)
    return None


def _extract_busy(obj: dict[str, Any]) -> bool:
    busy = obj.get("busy")
    if isinstance(busy, bool):
        return busy
    compacting = obj.get("isCompacting")
    if isinstance(compacting, bool) and compacting:
        return True
    streaming = obj.get("isStreaming")
    if isinstance(streaming, bool):
        return streaming
    return False


def _extract_is_compacting(obj: dict[str, Any]) -> bool:
    compacting = obj.get("isCompacting")
    return bool(compacting) if isinstance(compacting, bool) else False


def _extract_event_type(obj: dict[str, Any]) -> str:
    event_type = obj.get("type")
    if isinstance(event_type, str) and event_type:
        return event_type
    payload = obj.get("payload")
    if isinstance(payload, dict):
        payload_type = payload.get("type")
        if isinstance(payload_type, str):
            return payload_type
    return ""


def _event_output_text(event: dict[str, Any]) -> str:
    event_type = _extract_event_type(event)
    if event_type == "message.delta":
        delta = event.get("delta")
        return delta if isinstance(delta, str) else ""

    text = event.get("text")
    if isinstance(text, str) and text:
        suffix = "" if text.endswith("\n") else "\n"
        if event_type == "turn.started":
            return f"> {text}{suffix}"
        return text + suffix

    if event_type == "tool.started":
        tool_name = event.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            return f"\n[tool] {tool_name}\n"

    return ""


def _tail_delta(previous: str, current: str) -> str:
    if not current:
        return ""
    if not previous:
        return current
    if current.startswith(previous):
        return current[len(previous) :]

    max_overlap = min(len(previous), len(current))
    for overlap in range(max_overlap, 0, -1):
        if previous[-overlap:] == current[:overlap]:
            return current[overlap:]
    return current


def _request_flag(event: dict[str, Any], snake: str, camel: str, *, default: bool) -> bool:
    if snake in event:
        return bool(event.get(snake))
    if camel in event:
        return bool(event.get(camel))
    return default


def _request_timeout_ms(event: dict[str, Any]) -> int | None:
    for key in ("timeout_ms", "timeoutMs", "timeout"):
        value = event.get(key)
        if isinstance(value, int):
            return value
    return None


def _pending_ui_request_payload(
    *,
    request_id: str,
    method: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    options = event.get("options")
    return {
        "id": request_id,
        "method": method,
        "title": event.get("title"),
        "message": event.get("message"),
        "question": event.get("question") if isinstance(event.get("question"), str) else None,
        "context": event.get("context") if isinstance(event.get("context"), str) else None,
        "options": list(options) if isinstance(options, list) else [],
        "allow_freeform": _request_flag(
            event,
            "allow_freeform",
            "allowFreeform",
            default=method in {"select", "input", "editor"},
        ),
        "allow_multiple": _request_flag(
            event,
            "allow_multiple",
            "allowMultiple",
            default=False,
        ),
        "timeout_ms": _request_timeout_ms(event),
        "status": "pending",
    }


def _record_ui_request(st: "State", event: dict[str, Any]) -> None:
    request_id = event.get("id")
    if not isinstance(request_id, str) or not request_id:
        return
    method = event.get("method")
    if not isinstance(method, str) or method not in _DIALOG_UI_METHODS:
        return
    st.pending_ui_requests[request_id] = _pending_ui_request_payload(
        request_id=request_id,
        method=method,
        event=event,
    )


def _resume_session_id_from_agent_args(args: list[str]) -> str | None:
    for idx, token in enumerate(args):
        if token != "--session":
            continue
        if (idx + 1) >= len(args):
            return None
        raw = str(args[idx + 1] or "").strip()
        if (not raw) or raw.endswith(".jsonl"):
            return None
        return raw
    return None


def _ask_user_request_id_from_message(message: Any) -> str | None:
    if not isinstance(message, dict):
        return None
    if message.get("role") != "toolResult":
        return None
    if message.get("toolName") != "ask_user":
        return None
    tool_call_id = message.get("toolCallId")
    return tool_call_id if isinstance(tool_call_id, str) and tool_call_id else None


def _resolved_ui_request_ids(event: dict[str, Any]) -> set[str]:
    resolved_ids: set[str] = set()

    def _collect(container: Any) -> None:
        if not isinstance(container, dict):
            return
        direct = _ask_user_request_id_from_message(container)
        if direct:
            resolved_ids.add(direct)
        message = _ask_user_request_id_from_message(container.get("message"))
        if message:
            resolved_ids.add(message)
        tool_results = container.get("toolResults")
        if isinstance(tool_results, list):
            for item in tool_results:
                tool_call_id = _ask_user_request_id_from_message(item)
                if tool_call_id:
                    resolved_ids.add(tool_call_id)

    _collect(event)
    payload = event.get("payload")
    if isinstance(payload, dict):
        _collect(payload)
    return resolved_ids


def _live_stream_id(turn_id: str | None) -> str:
    return f"pi-stream:{turn_id or 'active'}"


def _live_event_ts(st: "State", event: dict[str, Any]) -> float:
    raw_ts = event.get("ts")
    if isinstance(raw_ts, (int, float)):
        return float(raw_ts)
    return float(st.start_ts)


def _live_pi_event(
    st: "State",
    *,
    summary: str,
    text: str | None = None,
    is_error: bool = False,
    event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "pi_event",
        "summary": summary,
        "ts": _live_event_ts(st, event or {}),
    }
    if text:
        payload["text"] = text
    if is_error:
        payload["is_error"] = True
    return payload


def _event_error_text(event: dict[str, Any]) -> str | None:
    for source in (event, event.get("payload") if isinstance(event.get("payload"), dict) else None):
        if not isinstance(source, dict):
            continue
        for key in ("errorMessage", "error", "message", "finalError"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None



def _retry_live_event(st: "State", event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = _extract_event_type(event)
    if event_type == "auto_retry_start":
        attempt = event.get("attempt") if isinstance(event.get("attempt"), int) else 1
        max_attempts = event.get("maxAttempts") if isinstance(event.get("maxAttempts"), int) else attempt
        error_text = _event_error_text(event)
        text = error_text or "Provider request failed. Retrying."
        return _live_pi_event(
            st,
            summary=f"Retrying request ({attempt}/{max_attempts})",
            text=text,
            is_error=True,
            event=event,
        )
    if event_type == "auto_retry_end" and event.get("success") is not True:
        return _live_pi_event(
            st,
            summary="Retry failed",
            text=_event_error_text(event) or "Retry attempts exhausted.",
            is_error=True,
            event=event,
        )
    return None



def _terminal_turn_live_event(
    st: "State",
    event: dict[str, Any],
    *,
    has_snapshot_text: bool,
) -> dict[str, Any] | None:
    event_type = _extract_event_type(event)
    error_text = _event_error_text(event)
    if event_type == "turn.failed":
        return _live_pi_event(
            st,
            summary="Turn failed",
            text=error_text or "Provider request failed.",
            is_error=True,
            event=event,
        )
    if event_type == "turn.aborted":
        return _live_pi_event(
            st,
            summary="Turn aborted",
            text=error_text,
            is_error=True,
            event=event,
        )
    if event_type in {"turn.completed", "turn_end"} and (not has_snapshot_text):
        return _live_pi_event(
            st,
            summary="Turn finished without assistant output",
            text="Pi ended the turn after tool or reasoning activity without a final assistant message.",
            is_error=True,
            event=event,
        )
    return None



def _compaction_start_summary(event: dict[str, Any]) -> str:
    reason = event.get("reason") if isinstance(event.get("reason"), str) else "manual"
    if reason == "overflow":
        return "Auto-compacting after context overflow"
    if reason == "threshold":
        return "Auto-compacting context"
    return "Compacting context"


def _compaction_end_live_event(st: "State", event: dict[str, Any]) -> dict[str, Any]:
    if event.get("aborted") is True:
        reason = event.get("reason") if isinstance(event.get("reason"), str) else "manual"
        summary = "Auto-compaction cancelled" if reason != "manual" else "Compaction cancelled"
        return _live_pi_event(st, summary=summary, event=event)

    error_message = _event_error_text(event)
    if error_message:
        return _live_pi_event(
            st,
            summary="Compaction failed",
            text=error_message,
            is_error=True,
            event=event,
        )

    result = event.get("result") if isinstance(event.get("result"), dict) else None
    summary_text = (
        result.get("summary")
        if isinstance(result, dict) and isinstance(result.get("summary"), str)
        else None
    )
    will_retry = event.get("willRetry") is True
    text = summary_text or ("Retrying with compacted context." if will_retry else None)
    return _live_pi_event(st, summary="Compaction finished", text=text, event=event)


def _compaction_live_event(st: "State", event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = _extract_event_type(event)
    if event_type == "compaction_start":
        return _live_pi_event(
            st,
            summary=_compaction_start_summary(event),
            text="New bridge messages wait until compaction finishes.",
            event=event,
        )
    if event_type != "compaction_end":
        return None
    return _compaction_end_live_event(st, event)


def _append_live_message_event(st: "State", event: dict[str, Any]) -> None:
    st.live_message_offset += 1
    st.live_message_events.append({"offset": st.live_message_offset, "event": event})


def _empty_output_terminal_event_key(st: "State", event: dict[str, Any]) -> str | None:
    event_type = _extract_event_type(event)
    if event_type not in {"turn.completed", "turn_end"}:
        return None
    turn_id = _extract_turn_id(event)
    if isinstance(turn_id, str) and turn_id:
        return f"turn:{turn_id}"
    if st.prompt_sent_at > 0:
        return f"prompt:{st.prompt_sent_at:.9f}"
    if isinstance(st.last_turn_id, str) and st.last_turn_id:
        return f"turn:{st.last_turn_id}"
    return f"fallback:{event_type}:{_live_event_ts(st, event):.6f}"


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


def _drain_rpc_stderr_into_tail(st: "State") -> None:
    stderr_lines: list[str] = []
    drain_stderr = getattr(st.rpc, "drain_stderr_lines", None)
    if callable(drain_stderr):
        try:
            raw_stderr_lines = drain_stderr()
            if isinstance(raw_stderr_lines, list):
                stderr_lines = [
                    line
                    for line in raw_stderr_lines
                    if isinstance(line, str) and line
                ]
            else:
                stderr_lines = []
        except Exception:
            stderr_lines = []
    for line in stderr_lines:
        suffix = "" if line.endswith("\n") else "\n"
        st.output_tail = (st.output_tail + f"[stderr] {line}{suffix}")[-st.output_tail_max :]


def _drain_rpc_events(st: "State") -> list[dict[str, Any]]:
    try:
        events = st.rpc.drain_events()
    except Exception:
        return []
    return events if isinstance(events, list) else []


def _handle_message_delta_event(
    st: "State",
    event: dict[str, Any],
    *,
    event_type: str,
    event_turn_id: str | None,
    stream_id: str,
) -> None:
    if event_type != "message.delta":
        return
    delta = event.get("delta") if isinstance(event.get("delta"), str) else ""
    if not delta:
        return
    snapshot = st.live_message_snapshots.get(stream_id)
    if snapshot is None:
        snapshot = {
            "role": "assistant",
            "text": "",
            "streaming": True,
            "stream_id": stream_id,
            "turn_id": event_turn_id,
            "ts": _live_event_ts(st, event),
        }
        st.live_message_snapshots[stream_id] = snapshot
    snapshot["text"] = f"{snapshot.get('text') or ''}{delta}"
    snapshot["turn_id"] = event_turn_id
    _append_live_message_event(st, dict(snapshot))


def _handle_retry_and_compaction_events(
    st: "State",
    event: dict[str, Any],
    *,
    event_type: str,
) -> None:
    retry_event = _retry_live_event(st, event)
    if retry_event is not None:
        _append_live_message_event(st, retry_event)

    compaction_event = _compaction_live_event(st, event)
    if compaction_event is None:
        return
    _append_live_message_event(st, compaction_event)
    if event_type == "compaction_start":
        st.is_compacting = True
        st.busy = True
    elif event_type == "compaction_end":
        st.is_compacting = False
        if (not st.last_turn_id) and st.prompt_sent_at <= 0.0 and event.get("willRetry") is not True:
            st.busy = False


def _handle_ui_request_events(st: "State", event: dict[str, Any], *, event_type: str) -> None:
    if event_type == "extension_ui_request":
        _record_ui_request(st, event)
    for request_id in _resolved_ui_request_ids(event):
        st.pending_ui_requests.pop(request_id, None)


def _clear_pending_ui_requests_for_terminal_match(
    st: "State",
    *,
    event_type: str,
    event_turn_id: str | None,
) -> None:
    terminal_event_matches_active_turn = (
        event_type in _TERMINAL_TURN_EVENT_TYPES
        and (
            (bool(event_turn_id) and st.last_turn_id == event_turn_id)
            or ((not event_turn_id) and (not st.last_turn_id) and st.prompt_sent_at <= 0.0)
        )
    )
    if terminal_event_matches_active_turn:
        st.pending_ui_requests.clear()


def _emit_terminal_turn_events(
    st: "State",
    event: dict[str, Any],
    *,
    event_type: str,
    stream_id: str,
) -> None:
    if event_type not in _TERMINAL_TURN_EVENT_TYPES:
        return
    snapshot = st.live_message_snapshots.get(stream_id)
    has_snapshot_text = bool(
        snapshot is not None
        and isinstance(snapshot.get("text"), str)
        and snapshot.get("text")
    )
    if has_snapshot_text and snapshot is not None:
        completed_snapshot = dict(snapshot)
        completed_snapshot["completed"] = True
        _append_live_message_event(st, completed_snapshot)
    terminal_event = _terminal_turn_live_event(
        st,
        event,
        has_snapshot_text=has_snapshot_text,
    )
    if terminal_event is None:
        return
    empty_output_key = _empty_output_terminal_event_key(st, event)
    if empty_output_key is None or empty_output_key != st.last_empty_output_event_key:
        _append_live_message_event(st, terminal_event)
        if empty_output_key is not None:
            st.last_empty_output_event_key = empty_output_key


def _append_output_tail_from_event(st: "State", event: dict[str, Any]) -> None:
    output = _event_output_text(event)
    if output:
        st.output_tail = (st.output_tail + output)[-st.output_tail_max :]


def _apply_turn_busy_state_transition(
    st: "State",
    event: dict[str, Any],
    *,
    event_type: str,
    event_turn_id: str | None,
) -> None:
    if not event_turn_id:
        if (
            event_type in _TERMINAL_TURN_EVENT_TYPES
            and (not st.last_turn_id)
            and st.prompt_sent_at <= 0.0
        ):
            st.busy = False
            st.prompt_sent_at = 0.0
            st.last_turn_id = None
        return
    if event_type in _TERMINAL_TURN_EVENT_TYPES:
        if st.last_turn_id == event_turn_id:
            st.busy = False
            st.prompt_sent_at = 0.0
        if st.last_turn_id == event_turn_id:
            st.last_turn_id = None
        return
    st.busy = True
    st.prompt_sent_at = 0.0
    st.last_turn_id = event_turn_id


@dataclass
class State:
    session_id: str | None
    codex_pid: int
    sock_path: Path
    session_path: Path | None
    start_ts: float
    rpc: PiRpcClient
    busy: bool = False
    output_tail: str = ""
    output_tail_max: int = 64 * 1024
    token: dict[str, Any] | None = None
    last_turn_id: str | None = None
    is_compacting: bool = False
    backend: str = "pi"
    # Monotonic timestamp of last successful prompt RPC.  Used to prevent
    # _sync_state_from_rpc from prematurely clearing the busy flag before
    # Pi has acknowledged the new turn.
    prompt_sent_at: float = 0.0
    pending_ui_requests: dict[str, dict[str, Any]] = field(default_factory=dict)
    live_message_offset: int = 0
    live_message_events: list[dict[str, Any]] = field(default_factory=list)
    live_message_snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_empty_output_event_key: str | None = None


class PiBroker:
    def __init__(
        self,
        *,
        cwd: str,
        session_path: Path | None = None,
        rpc: PiRpcClient | None = None,
        agent_args: list[str] | None = None,
        resume_session_id: str | None = None,
    ) -> None:
        self.cwd = cwd
        self.session_path = session_path
        self.rpc = rpc
        self.agent_args = list(agent_args or [])
        self.resume_session_id = (
            resume_session_id or _resume_session_id_from_agent_args(self.agent_args)
        )
        self.state: State | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._previous_sigint_handler: Any | None = None

    def _agent_args_manage_session(self) -> bool:
        return any(
            arg in {"--session", "--no-session", "--session-dir"}
            for arg in self.agent_args
        )

    def _write_meta(self) -> None:
        with self._lock:
            st = self.state
        if not st:
            return
        supports_web_control = "--no-session" not in self.agent_args
        meta = {
            "session_id": st.session_id,
            "backend": "pi",
            "transport": "pi-rpc",
            "tmux_session": (os.environ.get("CODEX_WEB_TMUX_SESSION") or "").strip()
            or None,
            "tmux_window": (os.environ.get("CODEX_WEB_TMUX_WINDOW") or "").strip()
            or None,
            "owner": OWNER_TAG if OWNER_TAG else None,
            "supports_web_control": supports_web_control,
            "supports_live_ui": True,
            "ui_protocol_version": 1,
            "broker_pid": os.getpid(),
            "agent_pid": st.codex_pid,
            "codex_pid": st.codex_pid,
            "cwd": self.cwd,
            "start_ts": float(st.start_ts),
            "log_path": None,
            "sock_path": str(st.sock_path),
            "resume_session_id": self.resume_session_id,
            "spawn_nonce": (os.environ.get("CODEX_WEB_SPAWN_NONCE") or "").strip()
            or None,
        }
        if st.session_path is not None:
            meta["session_path"] = str(st.session_path)
        SOCK_DIR.mkdir(parents=True, exist_ok=True)
        meta_path = st.sock_path.with_suffix(".json")
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(meta_path.parent), delete=False
        ) as tmp:
            tmp.write(json.dumps(meta))
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, meta_path)
        os.chmod(meta_path, 0o600)

    def _read_rpc_state_snapshot(self, st: State) -> dict[str, Any] | None:
        try:
            return st.rpc.get_state()
        except Exception:
            return None

    def _apply_rpc_busy_state_locked(
        self,
        st: State,
        *,
        rpc_state: dict[str, Any] | None,
    ) -> None:
        if not isinstance(rpc_state, dict):
            return
        st.is_compacting = _extract_is_compacting(rpc_state)
        rpc_busy = _extract_busy(rpc_state)
        # After a prompt is sent, Pi may not yet reflect busy=true
        # in its state. Keep the broker-side busy flag set briefly so
        # the frontend does not see an idle dip between accepted prompt
        # and turn start.
        if st.busy and not rpc_busy and st.prompt_sent_at > 0:
            elapsed = time.monotonic() - st.prompt_sent_at
            if elapsed < 5.0:
                rpc_busy = True
            else:
                st.prompt_sent_at = 0.0
        if rpc_busy:
            st.busy = True
            return
        st.busy = False
        st.prompt_sent_at = 0.0

    def _sync_rpc_ids_locked(
        self,
        st: State,
        *,
        rpc_state: dict[str, Any] | None,
    ) -> bool:
        rewrite_meta = False
        state_turn_id = _extract_turn_id(rpc_state) if isinstance(rpc_state, dict) else None
        if state_turn_id:
            st.last_turn_id = state_turn_id
        sid = _extract_session_id(rpc_state) if isinstance(rpc_state, dict) else None
        if isinstance(sid, str) and sid and sid != st.session_id:
            st.session_id = sid
            rewrite_meta = True
        if self.resume_session_id and (not st.busy) and (not st.last_turn_id):
            self.resume_session_id = None
            rewrite_meta = True
        return rewrite_meta

    def _sync_state_from_rpc(self) -> None:
        with self._lock:
            st = self.state
        if not st:
            return
        rpc_state = self._read_rpc_state_snapshot(st)
        rewrite_meta = False
        with self._lock:
            st2 = self.state
            if not st2:
                return
            self._apply_rpc_busy_state_locked(st2, rpc_state=rpc_state)
            self._drain_rpc_output_locked(st2)
            rewrite_meta = self._sync_rpc_ids_locked(st2, rpc_state=rpc_state)
        if rewrite_meta:
            self._write_meta()

    def _drain_rpc_output_locked(self, st: State) -> None:
        _drain_rpc_stderr_into_tail(st)
        for event in _drain_rpc_events(st):
            if not isinstance(event, dict):
                continue
            event_type = _extract_event_type(event)
            event_turn_id = _extract_turn_id(event)
            stream_id = _live_stream_id(event_turn_id)

            token_update = _pi_token_update(event)
            if token_update is not None:
                st.token = token_update

            _handle_message_delta_event(
                st,
                event,
                event_type=event_type,
                event_turn_id=event_turn_id,
                stream_id=stream_id,
            )
            _handle_retry_and_compaction_events(
                st,
                event,
                event_type=event_type,
            )
            _handle_ui_request_events(st, event, event_type=event_type)
            _clear_pending_ui_requests_for_terminal_match(
                st,
                event_type=event_type,
                event_turn_id=event_turn_id,
            )
            _emit_terminal_turn_events(
                st,
                event,
                event_type=event_type,
                stream_id=stream_id,
            )
            _append_output_tail_from_event(st, event)
            _apply_turn_busy_state_transition(
                st,
                event,
                event_type=event_type,
                event_turn_id=event_turn_id,
            )

    def _sync_output_from_rpc(self) -> None:
        with self._lock:
            st = self.state
            if not st:
                return
            self._drain_rpc_output_locked(st)

    def _get_state_snapshot(self) -> State | None:
        with self._lock:
            return self.state

    def _bg_sync_loop(self) -> None:
        """Background thread: periodically sync RPC state so socket handlers never block."""
        while not self._stop.is_set():
            try:
                self._sync_state_from_rpc()
            except Exception:
                pass
            self._stop.wait(1.0)

    def _mark_prompt_pending_locked(self, st: State) -> str | None:
        streaming_behavior: str | None = None
        if self.state is st:
            if st.busy:
                streaming_behavior = "steer"
            st.busy = True
            st.prompt_sent_at = time.monotonic()
            st.last_empty_output_event_key = None
        return streaming_behavior

    def _clear_prompt_pending_locked(self, st: State) -> None:
        if self.state is st:
            st.busy = False
            st.prompt_sent_at = 0.0

    def _apply_prompt_result_locked(self, st: State, result: dict[str, Any]) -> None:
        if self.state is st:
            st.last_turn_id = _extract_turn_id(result) or st.last_turn_id
            st.busy = True
            st.prompt_sent_at = time.monotonic()

    def _submit_terminal_prompt(self, text: str) -> dict[str, Any]:
        st = self._get_state_snapshot()
        if not st:
            raise RuntimeError("no state")
        with self._lock:
            streaming_behavior = self._mark_prompt_pending_locked(st)
        try:
            result = st.rpc.prompt(text, streaming_behavior=streaming_behavior)
        except Exception:
            with self._lock:
                self._clear_prompt_pending_locked(st)
            raise
        if not isinstance(result, dict):
            with self._lock:
                self._clear_prompt_pending_locked(st)
            raise RuntimeError("invalid prompt response")
        error = result.get("error")
        if isinstance(error, str) and error:
            with self._lock:
                self._clear_prompt_pending_locked(st)
            raise RuntimeError(error)
        with self._lock:
            self._apply_prompt_result_locked(st, result)
        return result

    def _interrupt_terminal_turn(self) -> dict[str, Any]:
        st = self._get_state_snapshot()
        if not st:
            raise RuntimeError("no state")
        result = st.rpc.abort(None)
        with self._lock:
            if self.state is st:
                st.busy = False
                st.last_turn_id = None
                st.prompt_sent_at = 0.0
        return result

    def _stdin_loop(self) -> None:
        while not self._stop.is_set():
            try:
                line = sys.stdin.readline()
            except KeyboardInterrupt:
                try:
                    self._interrupt_terminal_turn()
                except Exception as exc:
                    sys.stderr.write(f"[pi-broker] {exc}\n")
                    sys.stderr.flush()
                continue
            except Exception:
                self._stop.set()
                return
            if line == "":
                self._stop.set()
                return
            text = line.rstrip("\r\n")
            if not text.strip():
                continue
            try:
                self._submit_terminal_prompt(text)
            except Exception as exc:
                sys.stderr.write(f"[pi-broker] {exc}\n")
                sys.stderr.flush()

    def _stdout_loop(self) -> None:
        last_tail = ""
        while not self._stop.is_set():
            try:
                self._sync_output_from_rpc()
                with self._lock:
                    st = self.state
                    tail = st.output_tail if st else ""
            except Exception:
                tail = ""
            if tail:
                chunk = _tail_delta(last_tail, tail)
                if chunk:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                last_tail = tail
            self._stop.wait(0.1)

    def _delegate_sigint(self, frame: Any | None) -> None:
        previous = self._previous_sigint_handler
        if previous in (None, signal.SIG_IGN):
            return
        if previous is signal.SIG_DFL:
            signal.default_int_handler(signal.SIGINT, frame)
            return
        if callable(previous):
            previous(signal.SIGINT, frame)

    def _handle_sigint(self, _signum: int, _frame: Any | None) -> None:
        st = self._get_state_snapshot()
        if not st or not st.busy:
            self._delegate_sigint(_frame)
            return
        try:
            self._interrupt_terminal_turn()
        except Exception as exc:
            sys.stderr.write(f"[pi-broker] {exc}\n")
            sys.stderr.flush()
            self._delegate_sigint(_frame)

    def _close(self) -> None:
        self._stop.set()
        with self._lock:
            st = self.state
        if st is not None:
            st.rpc.close()


    def _cmd_state(self, conn: socket.socket, _req: dict[str, Any]) -> None:
        with self._lock:
            st = self.state
            if st is not None:
                self._drain_rpc_output_locked(st)
            resp = {
                "busy": bool(st.busy) if st else False,
                "queue_len": 0,
                "token": st.token if st else None,
                "isCompacting": bool(st.is_compacting) if st else False,
            }
        _send_socket_json_line(conn, resp)

    def _cmd_tail(self, conn: socket.socket, _req: dict[str, Any]) -> None:
        with self._lock:
            st = self.state
            if st is not None:
                self._drain_rpc_output_locked(st)
            resp = {"tail": st.output_tail if st else ""}
        _send_socket_json_line(conn, resp)

    def _cmd_live_messages(self, conn: socket.socket, req: dict[str, Any]) -> None:
        raw_offset = req.get("offset")
        since_offset = int(raw_offset) if isinstance(raw_offset, int) else 0
        with self._lock:
            st = self.state
            if st is not None:
                self._drain_rpc_output_locked(st)
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
        with self._lock:
            st = self.state
            if st is not None:
                self._drain_rpc_output_locked(st)
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
        with self._lock:
            st = self.state
            if st is not None:
                self._drain_rpc_output_locked(st)
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
        with self._lock:
            st = self.state
            if st is not None:
                self._drain_rpc_output_locked(st)
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
    ) -> tuple[State, dict[str, Any], Any]:
        with self._lock:
            st = self.state
            if not st:
                raise RuntimeError("no state")
            pending = st.pending_ui_requests.get(request_id)
            if pending is None:
                raise ValueError("unknown or expired request")
            if pending.get("status") != "pending":
                raise RuntimeError("request already resolved")
            pending["status"] = "resolved"
            rpc = st.rpc
        return st, pending, rpc

    def _restore_pending_ui_request_on_failure(
        self,
        *,
        request_id: str,
        expected_pending: dict[str, Any],
    ) -> None:
        with self._lock:
            st = self.state
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
            _st, pending, rpc = self._resolve_pending_ui_request(request_id)
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
        self._submit_terminal_prompt(text)
        _send_socket_json_line(conn, {"queued": False, "queue_len": 0})

    def _cmd_keys(self, conn: socket.socket, req: dict[str, Any]) -> None:
        seq_raw = req.get("seq")
        if not isinstance(seq_raw, str) or not seq_raw:
            _send_socket_json_line(conn, {"error": "seq required"})
            return
        seq = _seq_bytes(seq_raw)
        with self._lock:
            st = self.state
            if not st:
                _send_socket_json_line(conn, {"error": "no state"})
                return
        if seq != b"\x1b":
            _send_socket_json_line(conn, {"error": f"unsupported key sequence: {seq_raw}"})
            return
        self._interrupt_terminal_turn()
        _send_socket_json_line(conn, {"ok": True, "queued": False, "n": len(seq)})

    def _cmd_shutdown(self, conn: socket.socket, _req: dict[str, Any]) -> None:
        _send_socket_json_line(conn, {"ok": True})
        self._close()

    def _dispatch_conn_command(
        self,
        conn: socket.socket,
        cmd: Any,
        req: dict[str, Any],
    ) -> bool:
        handlers = {
            "state": self._cmd_state,
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

    def _read_conn_request(self, conn: socket.socket) -> dict[str, Any] | None:
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

    def _send_conn_error(self, conn: socket.socket, exc: Exception) -> None:
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

    def _handle_conn(self, conn: socket.socket) -> None:
        try:
            req = self._read_conn_request(conn)
            if req is None:
                return
            cmd = req.get("cmd")
            if self._dispatch_conn_command(conn, cmd, req):
                return
            _send_socket_json_line(conn, {"error": "unknown cmd"})
        except Exception as exc:
            self._send_conn_error(conn, exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _sock_server(self) -> None:
        with self._lock:
            st = self.state
        if not st:
            return
        SOCK_DIR.mkdir(parents=True, exist_ok=True)
        if st.sock_path.exists():
            st.sock_path.unlink()
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(st.sock_path))
        os.chmod(st.sock_path, 0o600)
        srv.listen(20)
        srv.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except Exception:
                break
            threading.Thread(
                target=self._handle_conn, args=(conn,), daemon=True
            ).start()
        try:
            srv.close()
        except Exception:
            pass

    def _init_runtime_state(self) -> tuple[Path | None, State]:
        SOCK_DIR.mkdir(parents=True, exist_ok=True)
        PI_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        session_path = self.session_path
        if session_path is None and not self._agent_args_manage_session():
            session_path = PI_SESSION_DIR / f"{token}.jsonl"
        sock_path = SOCK_DIR / f"{token}.sock"
        rpc = self.rpc or PiRpcClient(
            cwd=self.cwd,
            session_path=session_path,
            agent_args=self.agent_args,
        )
        rpc_pid = getattr(rpc, "pid", None)
        state = State(
            session_id=None,
            codex_pid=rpc_pid or os.getpid(),
            sock_path=sock_path,
            session_path=session_path,
            start_ts=time.time(),
            rpc=rpc,
        )
        self.state = state
        return session_path, state

    def _start_runtime_threads(self, *, foreground: bool) -> threading.Thread:
        self._write_meta()
        threading.Thread(target=self._bg_sync_loop, name="pi-bg-sync", daemon=True).start()
        self._previous_sigint_handler = None
        if foreground and sys.stdin.isatty() and sys.stdout.isatty():
            self._previous_sigint_handler = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, self._handle_sigint)
            threading.Thread(target=self._stdin_loop, name="pi-stdin", daemon=True).start()
            threading.Thread(target=self._stdout_loop, name="pi-stdout", daemon=True).start()
        sock_thread = threading.Thread(target=self._sock_server, name="pi-sock-server", daemon=True)
        sock_thread.start()
        return sock_thread

    def _wait_runtime_exit(self, *, rpc: Any, sock_thread: threading.Thread) -> int:
        proc = getattr(rpc, "_proc", None)
        if proc is None or not hasattr(proc, "poll"):
            sock_thread.join()
            return 0
        exit_code = 0
        while not self._stop.is_set():
            code = proc.poll()
            if code is not None:
                exit_code = int(code)
                self._stop.set()
                break
            if not sock_thread.is_alive():
                self._stop.set()
                break
            time.sleep(0.1)
        return exit_code

    def _finalize_runtime(self, *, sock_thread: threading.Thread) -> None:
        self._stop.set()
        sock_thread.join(timeout=1.0)
        if self._previous_sigint_handler is not None:
            signal.signal(signal.SIGINT, self._previous_sigint_handler)
            self._previous_sigint_handler = None
        self._close()

    def run(self, *, foreground: bool = True) -> int:
        _session_path, state = self._init_runtime_state()
        sock_thread = self._start_runtime_threads(foreground=foreground)
        try:
            return self._wait_runtime_exit(rpc=state.rpc, sock_thread=sock_thread)
        finally:
            self._finalize_runtime(sock_thread=sock_thread)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--session-file")
    ap.add_argument("args", nargs=argparse.REMAINDER)
    ns = ap.parse_args()
    session_path = (
        Path(ns.session_file).expanduser().resolve() if ns.session_file else None
    )
    args = list(ns.args)
    if args and args[0] == "--":
        args = args[1:]
    raise SystemExit(
        PiBroker(cwd=ns.cwd, session_path=session_path, agent_args=args).run()
    )


if __name__ == "__main__":
    main()
