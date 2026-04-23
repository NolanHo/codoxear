from __future__ import annotations

import re
from typing import Any, Protocol

from codoxear.pi_log import (
    pi_assistant_is_final_turn_end as _pi_assistant_is_final_turn_end,
)
from codoxear.pi_log import pi_assistant_text as _pi_assistant_text
from codoxear.pi_log import pi_assistant_thinking_count as _pi_assistant_thinking_count
from codoxear.pi_log import pi_assistant_tool_use_count as _pi_assistant_tool_use_count
from codoxear.pi_log import pi_message_role as _pi_message_role
from codoxear.pi_log import pi_user_text as _pi_user_text


class BrokerStateLike(Protocol):
    busy: bool
    pending_calls: set[str]
    turn_open: bool
    turn_has_completion_candidate: bool
    last_interrupt_hint_ts: float
    last_turn_activity_ts: float
    interrupt_hint_tail: str
    interrupt_hint_tail_max: int


_ANSI_OSC_RE = re.compile("\x1b\\][^\x07]*(?:\x07|\x1b\\\\)")
_ANSI_CSI_RE = re.compile("\x1b(?:[@-Z\\-_]|\\[[0-?]*[ -/]*[@-~])")
_RESPONSE_ITEM_ACTIVITY_TYPES = {
    "reasoning",
    "function_call",
    "function_call_output",
    "custom_tool_call",
    "custom_tool_call_output",
    "web_search_call",
    "local_shell_call",
}


def strip_ansi(text: str) -> str:
    return _ANSI_CSI_RE.sub("", _ANSI_OSC_RE.sub("", text))


def _hint_seen_in_new_text(*, tail: str, cleaned: str, phrase: str) -> bool:
    low_cleaned = cleaned.lower()
    low_phrase = phrase.lower()
    if low_phrase in low_cleaned:
        return True
    overlap = max(len(low_phrase) - 1, 0)
    if overlap <= 0:
        return False
    stitched = tail[-overlap:].lower() + low_cleaned
    pos = stitched.find(low_phrase)
    if pos < 0:
        return False
    return (pos + len(low_phrase)) > overlap


def _interrupt_hint_seen_in_new_text(*, tail: str, cleaned: str) -> bool:
    return _hint_seen_in_new_text(tail=tail, cleaned=cleaned, phrase="esc to interrupt")


def _compacting_hint_seen_in_new_text(*, tail: str, cleaned: str) -> bool:
    return _hint_seen_in_new_text(
        tail=tail, cleaned=cleaned, phrase="compacting context"
    ) or _hint_seen_in_new_text(
        tail=tail, cleaned=cleaned, phrase="compacting conversation"
    )


def update_busy_from_pty_text(
    st: BrokerStateLike,
    text: str,
    *,
    now_ts: float,
) -> None:
    cleaned = strip_ansi(text)
    if not cleaned:
        return
    tail = st.interrupt_hint_tail
    st.interrupt_hint_tail = (st.interrupt_hint_tail + cleaned)[
        -st.interrupt_hint_tail_max :
    ]
    if _interrupt_hint_seen_in_new_text(tail=tail, cleaned=cleaned):
        st.busy = True
        st.last_interrupt_hint_ts = now_ts
        if now_ts > st.last_turn_activity_ts:
            st.last_turn_activity_ts = now_ts
        return
    if _compacting_hint_seen_in_new_text(tail=tail, cleaned=cleaned):
        st.busy = True
        if now_ts > st.last_turn_activity_ts:
            st.last_turn_activity_ts = now_ts


def _response_call_started(payload: dict[str, Any]) -> str | None:
    t = payload.get("type")
    if t not in ("function_call", "custom_tool_call"):
        return None
    call_id = payload.get("call_id")
    return call_id if isinstance(call_id, str) and call_id else None


def _response_call_finished(payload: dict[str, Any]) -> str | None:
    t = payload.get("type")
    if t not in ("function_call_output", "custom_tool_call_output"):
        return None
    call_id = payload.get("call_id")
    return call_id if isinstance(call_id, str) and call_id else None


def should_clear_busy_state(
    st: BrokerStateLike,
    now_ts: float,
    *,
    quiet_seconds: float,
    interrupt_grace_seconds: float,
) -> bool:
    if not st.busy:
        return False
    if st.pending_calls:
        return False
    if st.turn_open and (not st.turn_has_completion_candidate):
        return False
    if (
        st.last_interrupt_hint_ts > 0.0
        and (now_ts - st.last_interrupt_hint_ts) < interrupt_grace_seconds
    ):
        return False
    if st.last_turn_activity_ts <= 0.0:
        return False
    return (now_ts - st.last_turn_activity_ts) >= quiet_seconds


def _reopen_turn_on_activity(st: BrokerStateLike) -> None:
    if st.turn_open:
        return
    st.turn_open = True
    st.turn_has_completion_candidate = False


def _close_turn_state(st: BrokerStateLike) -> None:
    st.pending_calls.clear()
    st.busy = False
    st.turn_open = False
    st.turn_has_completion_candidate = False
    st.last_interrupt_hint_ts = 0.0
    st.last_turn_activity_ts = 0.0


def _mark_user_turn_activity(st: BrokerStateLike, now_ts: float) -> None:
    st.pending_calls.clear()
    st.busy = True
    st.turn_open = True
    st.turn_has_completion_candidate = False
    st.last_interrupt_hint_ts = 0.0
    st.last_turn_activity_ts = now_ts


def _mark_turn_activity(
    st: BrokerStateLike,
    now_ts: float,
    *,
    clear_completion: bool,
) -> None:
    _reopen_turn_on_activity(st)
    if clear_completion and st.turn_open:
        st.turn_has_completion_candidate = False
    st.busy = True
    st.last_turn_activity_ts = now_ts


def _apply_event_msg_to_state(
    st: BrokerStateLike,
    payload: dict[str, Any],
    *,
    now_ts: float,
) -> None:
    ev_type = payload.get("type")
    if ev_type == "user_message":
        msg = payload.get("message")
        if isinstance(msg, str) and msg.strip():
            _mark_user_turn_activity(st, now_ts)
        return
    if ev_type in {"turn_aborted", "thread_rolled_back", "task_complete"}:
        _close_turn_state(st)
        return
    if ev_type == "agent_message":
        msg = payload.get("message")
        if isinstance(msg, str) and msg.strip() and st.turn_open:
            st.turn_has_completion_candidate = True
        st.busy = True
        st.last_turn_activity_ts = now_ts
        return
    if ev_type == "agent_reasoning":
        _mark_turn_activity(st, now_ts, clear_completion=True)
        return
    if ev_type == "token_count" and st.busy:
        st.last_turn_activity_ts = now_ts


def _apply_message_obj_to_state(
    st: BrokerStateLike,
    obj: dict[str, Any],
    *,
    now_ts: float,
) -> None:
    user_text = _pi_user_text(obj)
    if isinstance(user_text, str) and user_text:
        _mark_user_turn_activity(st, now_ts)
        return

    role = _pi_message_role(obj)
    has_text = bool(_pi_assistant_text(obj))
    thinking_count = _pi_assistant_thinking_count(obj)
    tool_count = _pi_assistant_tool_use_count(obj)
    is_tool_result = role == "toolResult"

    if has_text and role == "assistant" and _pi_assistant_is_final_turn_end(obj):
        _close_turn_state(st)
        return

    if is_tool_result or tool_count > 0 or thinking_count > 0:
        _mark_turn_activity(st, now_ts, clear_completion=True)


def _apply_response_item_to_state(
    st: BrokerStateLike,
    payload: dict[str, Any],
    *,
    now_ts: float,
) -> None:
    started = _response_call_started(payload)
    if started is not None:
        st.pending_calls.add(started)
        _mark_turn_activity(st, now_ts, clear_completion=True)
        return

    finished = _response_call_finished(payload)
    if finished is not None:
        st.pending_calls.discard(finished)
        _mark_turn_activity(st, now_ts, clear_completion=True)
        return

    item_type = payload.get("type")
    role = payload.get("role")
    if item_type in _RESPONSE_ITEM_ACTIVITY_TYPES:
        _mark_turn_activity(st, now_ts, clear_completion=True)
        return

    if item_type == "message" and role == "assistant":
        content = payload.get("content")
        if not isinstance(content, list):
            raise ValueError("invalid assistant message content")
        has_text = any(
            isinstance(part, dict)
            and part.get("type") == "output_text"
            and isinstance(part.get("text"), str)
            and part.get("text")
            for part in content
        )
        if has_text and st.turn_open:
            st.turn_has_completion_candidate = True
        st.busy = True
        st.last_turn_activity_ts = now_ts


def apply_rollout_obj_to_state(
    st: BrokerStateLike,
    obj: dict[str, Any],
    *,
    now_ts: float,
) -> None:
    typ = obj.get("type")

    if typ == "event_msg":
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("invalid rollout event_msg payload")
        _apply_event_msg_to_state(st, payload, now_ts=now_ts)
        return

    if typ == "message":
        _apply_message_obj_to_state(st, obj, now_ts=now_ts)
        return

    if typ != "response_item":
        return

    payload = obj.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("invalid rollout response_item payload")
    _apply_response_item_to_state(st, payload, now_ts=now_ts)
