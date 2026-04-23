from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Session:
    session_id: str
    thread_id: str
    broker_pid: int
    codex_pid: int
    agent_backend: str
    owned: bool
    start_ts: float
    cwd: str
    log_path: Path | None
    sock_path: Path
    session_path: Path | None = None
    backend: str = "codex"
    busy: bool = False
    queue_len: int = 0
    token: dict[str, Any] | None = None
    last_turn_id: str | None = None
    last_chat_ts: float | None = None
    last_chat_history_scanned: bool = False
    meta_thinking: int = 0
    meta_tools: int = 0
    meta_system: int = 0
    meta_log_off: int = 0
    chat_index_events: list[dict[str, Any]] = field(default_factory=list)
    chat_index_scan_bytes: int = 0
    chat_index_scan_complete: bool = False
    chat_index_log_off: int = 0
    delivery_log_off: int = 0
    idle_cache_log_off: int = -1
    idle_cache_value: bool | None = None
    queue_idle_since: float | None = None
    model_provider: str | None = None
    preferred_auth_method: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    service_tier: str | None = None
    transport: str | None = None
    supports_live_ui: bool | None = None
    ui_protocol_version: int | None = None
    tmux_session: str | None = None
    tmux_window: str | None = None
    resume_session_id: str | None = None
    title: str | None = None
    first_user_message: str | None = None
    pi_idle_activity_ts: float | None = None
    pi_busy_activity_floor: float | None = None
    pi_session_path_discovered: bool = False
    pi_attention_scan_activity_ts: float | None = None
    bridge_transport_state: str = "unknown"
    bridge_transport_error: str | None = None
    bridge_transport_checked_ts: float = 0.0


@dataclass
class BridgeOutboundRequest:
    request_id: str
    runtime_id: str
    durable_session_id: str
    text: str
    created_ts: float
    state: str = "queued"
    attempts: int = 0
    last_error: str | None = None
    last_attempt_ts: float = 0.0
