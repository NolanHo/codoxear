from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from ..runtime import ServerRuntime


@dataclass(slots=True)
class SessionLivePayloadService:
    runtime: ServerRuntime
    manager: Any

    def session_live_payload(
        self,
        session_id: str,
        *,
        offset: int = 0,
        live_offset: int = 0,
        bridge_offset: int = 0,
        requests_version: str | None = None,
    ) -> dict[str, Any]:
        return session_live_payload(
            self.runtime,
            self.manager,
            session_id,
            offset=offset,
            live_offset=live_offset,
            bridge_offset=bridge_offset,
            requests_version=requests_version,
        )

    def pi_live_messages_payload(self, session: Any, *, offset: int = 0) -> dict[str, Any]:
        return pi_live_messages_payload(
            self.runtime,
            self.manager,
            session,
            offset=offset,
        )

    def merge_pi_live_message_events(
        self,
        durable_events: list[dict[str, Any]],
        streamed_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return merge_pi_live_message_events(
            self.runtime,
            durable_events,
            streamed_events,
        )


def service(runtime: ServerRuntime, manager: Any) -> SessionLivePayloadService:
    return SessionLivePayloadService(runtime, manager)


def session_live_payload(
    runtime: ServerRuntime,
    manager: Any,
    session_id: str,
    *,
    offset: int = 0,
    live_offset: int = 0,
    bridge_offset: int = 0,
    requests_version: str | None = None,
) -> dict[str, Any]:
    sv = runtime
    manager.refresh_session_meta(session_id, strict=False)
    s = manager.get_session(session_id)
    if not s:
        historical_row = sv.api.session_listing.service(sv).historical_session_row(session_id)
        if historical_row is None:
            historical_row = sv.api.listed_session_row(manager, session_id)
        if historical_row is None:
            raise KeyError("unknown session")
        try:
            page = manager.get_messages_page(
                session_id,
                offset=max(0, int(offset)),
                init=(offset <= 0),
                limit=sv.api.SESSION_HISTORY_PAGE_SIZE,
                before=0,
            )
        except KeyError:
            page = {
                "events": [],
                "offset": max(0, int(offset)),
                "has_older": False,
                "next_before": 0,
            }
        durable_session_id = str(historical_row.get("session_id") or session_id)
        bridge_session_key = sv.api.clean_optional_text(historical_row.get("resume_session_id")) or durable_session_id
        bridge_events, next_bridge_offset = manager.bridge_events_since(
            bridge_session_key,
            offset=bridge_offset,
        )
        base_events = page.get("events") if isinstance(page.get("events"), list) else []
        merged_events = merge_events_by_ts(base_events, bridge_events)
        return {
            "ok": True,
            "session_id": durable_session_id,
            "runtime_id": None,
            "offset": int(page.get("offset", max(0, int(offset))) or 0),
            "live_offset": 0,
            "bridge_offset": next_bridge_offset,
            "has_older": bool(page.get("has_older")),
            "next_before": int(page.get("next_before", 0) or 0),
            "busy": False,
            "events": merged_events,
            "requests_version": "",
            "requests": [],
            "token": None,
            "context_usage": None,
            "turn_timing": None,
        }
    page = manager.get_messages_page(
        session_id,
        offset=max(0, int(offset)),
        init=(offset <= 0),
        limit=sv.api.SESSION_HISTORY_PAGE_SIZE,
        before=0,
    )
    state = manager.get_state(session_id)
    busy, _broker_busy = sv.api.session_display.service(sv).display_session_busy(manager, session_id, s, state)
    state_token = state.get("token") if isinstance(state, dict) else None
    token_val = sv.api.session_display.service(sv).resolved_session_token(
        s,
        state_token if isinstance(state_token, dict) else None,
    )
    session_stats = manager.get_session_stats(session_id) if s.backend == "pi" else None
    requests: list[dict[str, Any]] = []
    if s.backend == "pi":
        requests_payload = manager.get_ui_state(session_id)
        live_requests = requests_payload.get("requests")
        if isinstance(live_requests, list):
            requests = [item for item in live_requests if isinstance(item, dict)]
    current_requests_version = sv.api.ui_requests_version(requests)
    events = page.get("events")
    merged_events = events if isinstance(events, list) else []
    next_live_offset = max(0, int(live_offset))
    next_bridge_offset = max(0, int(bridge_offset))
    if sv.api.session_display.service(sv).session_supports_live_pi_ui(s):
        streamed_payload = pi_live_messages_payload(runtime, manager, s, offset=live_offset)
        next_live_offset = int(streamed_payload.get("offset", max(0, int(live_offset))) or max(0, int(live_offset)))
        merged_events = merge_pi_live_message_events(
            runtime,
            merged_events,
            [item for item in (streamed_payload.get("events") or []) if isinstance(item, dict)],
        )
    bridge_events, next_bridge_offset = manager.bridge_events_since(
        sv.api.session_display.service(sv).durable_session_id_for_live_session(s),
        offset=bridge_offset,
    )
    if bridge_events:
        merged_events = merge_events_by_ts(merged_events, bridge_events)
    payload: dict[str, Any] = {
        "ok": True,
        "session_id": sv.api.session_display.service(sv).durable_session_id_for_live_session(s),
        "runtime_id": s.session_id,
        "offset": int(page.get("offset", max(0, int(offset))) or 0),
        "live_offset": next_live_offset,
        "bridge_offset": next_bridge_offset,
        "has_older": bool(page.get("has_older")),
        "next_before": int(page.get("next_before", 0) or 0),
        "busy": bool(busy),
        "events": merged_events,
        "requests_version": current_requests_version,
        "token": token_val,
        "context_usage": sv.api.session_payloads.service(sv).session_context_usage_from_stats(
            session_stats
        ),
        "turn_timing": sv.api.session_payloads.service(sv).session_turn_timing_payload(
            s,
            merged_events,
            busy=bool(busy),
        ),
        "transport_state": s.bridge_transport_state,
        "transport_error": s.bridge_transport_error,
    }
    if requests_version != current_requests_version:
        payload["requests"] = requests
    return payload



def pi_live_messages_payload(runtime: ServerRuntime, manager: Any, session: Any, *, offset: int = 0) -> dict[str, Any]:
    sv = runtime
    if not sv.api.session_display.service(sv).session_supports_live_pi_ui(session):
        return {"offset": max(0, int(offset)), "events": []}
    try:
        payload = manager.sock_call(
            session.sock_path,
            {"cmd": "live_messages", "offset": max(0, int(offset))},
            timeout_s=1.5,
        )
    except Exception:
        return {"offset": max(0, int(offset)), "events": []}
    events = payload.get("events")
    return {
        "offset": int(payload.get("offset", max(0, int(offset))) or 0),
        "events": [item for item in events if isinstance(item, dict)] if isinstance(events, list) else [],
    }



def _parse_iso8601_to_epoch(raw: str) -> float | None:
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None



def _event_ts(event: dict[str, Any]) -> float | None:
    for key in ("ts", "timestamp", "created_at", "updated_at"):
        value = event.get(key)
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1_000_000_000_000.0:
                ts /= 1000.0
            return ts
        if isinstance(value, str):
            parsed = _parse_iso8601_to_epoch(value)
            if parsed is not None:
                return float(parsed)
    return None



def _event_sort_timestamps(events: list[dict[str, Any]]) -> tuple[list[float], float | None]:
    out: list[float] = []
    last_seen: float | None = None
    for event in events:
        ts = _event_ts(event)
        if ts is None:
            ts = (last_seen + 1e-6) if last_seen is not None else 1e-6
        out.append(float(ts))
        if last_seen is None or ts > last_seen:
            last_seen = float(ts)
    return out, last_seen



def _insert_event_by_ts(
    merged: list[dict[str, Any]], event: dict[str, Any]
) -> None:
    existing_ts, max_ts = _event_sort_timestamps(merged)
    ts = _event_ts(event)
    event_ts = float(ts) if ts is not None else ((max_ts + 1e-6) if max_ts is not None else 1e-6)
    insert_at = len(merged)
    while insert_at > 0:
        prev_ts = existing_ts[insert_at - 1]
        if prev_ts <= event_ts:
            break
        insert_at -= 1
    merged.insert(insert_at, event)



def _collapse_bridge_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_event_id: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for event in events:
        event_id = str(event.get("event_id") or "").strip()
        if not event_id:
            ordered.append(event)
            continue
        latest_by_event_id[event_id] = event
    emitted_event_ids: set[str] = set()
    collapsed: list[dict[str, Any]] = []
    for event in events:
        event_id = str(event.get("event_id") or "").strip()
        if not event_id:
            collapsed.append(event)
            continue
        if event_id in emitted_event_ids:
            continue
        latest = latest_by_event_id.get(event_id)
        if latest is None:
            continue
        collapsed.append(latest)
        emitted_event_ids.add(event_id)
    return collapsed


def merge_events_by_ts(
    durable_events: list[dict[str, Any]], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged = list(durable_events)
    for event in _collapse_bridge_events(events):
        _insert_event_by_ts(merged, event)
    return merged


def merge_pi_live_message_events(
    runtime: ServerRuntime,
    durable_events: list[dict[str, Any]],
    streamed_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(durable_events)
    durable_turn_ids = {
        str(event.get("turn_id"))
        for event in durable_events
        if event.get("role") == "assistant"
        and isinstance(event.get("turn_id"), str)
        and str(event.get("turn_id") or "")
    }
    tail_durable_text = ""
    for event in reversed(durable_events):
        if event.get("role") != "assistant":
            if event.get("role") == "user":
                break
            continue
        text = event.get("text")
        if isinstance(text, str) and text.strip():
            tail_durable_text = text.strip()
            break
    for event in streamed_events:
        if event.get("role") != "assistant":
            _insert_event_by_ts(merged, event)
            continue
        turn_id = event.get("turn_id") if isinstance(event.get("turn_id"), str) else None
        text = str(event.get("text") or "").strip()
        if turn_id and turn_id in durable_turn_ids:
            continue
        if bool(event.get("completed")) and text and text == tail_durable_text:
            continue
        _insert_event_by_ts(merged, event)
    return merged
