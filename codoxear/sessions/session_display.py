from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from types import FunctionType
from typing import Any

from ..runtime import ServerRuntime


def _runtime_wrapper(runtime: ServerRuntime, name: str) -> Any | None:
    module = getattr(runtime, "module", None)
    if module is None:
        return None
    wrapper = getattr(module, name, None)
    if not callable(wrapper):
        return None
    if (
        isinstance(wrapper, FunctionType)
        and getattr(wrapper, "__module__", None) == getattr(module, "__name__", None)
        and getattr(wrapper, "__name__", None) == name
    ):
        return None
    return wrapper


@dataclass(slots=True)
class SessionDisplayService:
    runtime: ServerRuntime

    def session_supports_live_pi_ui(self, session: Any) -> bool:
        wrapper = _runtime_wrapper(self.runtime, "_session_supports_live_pi_ui")
        if wrapper is not None:
            return wrapper(session)
        return session_supports_live_pi_ui(session)

    def is_attention_worthy_session_event(self, event: dict[str, Any]) -> bool:
        wrapper = _runtime_wrapper(self.runtime, "_is_attention_worthy_session_event")
        if wrapper is not None:
            return wrapper(event)
        return is_attention_worthy_session_event(event)

    def attention_updated_ts_from_events(
        self,
        events: list[dict[str, Any]],
    ) -> float | None:
        wrapper = _runtime_wrapper(self.runtime, "_attention_updated_ts_from_events")
        if wrapper is not None:
            return wrapper(events)
        return attention_updated_ts_from_events(events)

    def last_attention_ts_from_pi_tail(
        self,
        session_path: Path | None,
        *,
        max_scan_bytes: int = 8 * 1024 * 1024,
    ) -> float | None:
        wrapper = _runtime_wrapper(self.runtime, "_last_attention_ts_from_pi_tail")
        if wrapper is not None:
            return wrapper(session_path, max_scan_bytes=max_scan_bytes)
        return last_attention_ts_from_pi_tail(
            self.runtime,
            session_path,
            max_scan_bytes=max_scan_bytes,
        )

    def display_updated_ts(self, session: Any) -> float:
        wrapper = _runtime_wrapper(self.runtime, "_display_updated_ts")
        if wrapper is not None:
            return wrapper(session)
        return display_updated_ts(session)

    def session_row_dedupe_key(self, row: dict[str, Any]) -> str:
        wrapper = _runtime_wrapper(self.runtime, "_session_row_dedupe_key")
        if wrapper is not None:
            return wrapper(row)
        return session_row_dedupe_key(self.runtime, row)

    def display_source_path(self, session: Any) -> str | None:
        wrapper = _runtime_wrapper(self.runtime, "_display_source_path")
        if wrapper is not None:
            return wrapper(session)
        return display_source_path(session)

    def durable_session_id_for_live_session(self, session: Any) -> str:
        wrapper = _runtime_wrapper(self.runtime, "_durable_session_id_for_live_session")
        if wrapper is not None:
            return wrapper(session)
        return durable_session_id_for_live_session(self.runtime, session)

    def display_pi_busy(self, session: Any, *, broker_busy: bool) -> bool:
        wrapper = _runtime_wrapper(self.runtime, "_display_pi_busy")
        if wrapper is not None:
            return wrapper(session, broker_busy=broker_busy)
        return display_pi_busy(self.runtime, session, broker_busy=broker_busy)

    def validated_session_state(
        self,
        state: dict[str, Any] | Any,
    ) -> dict[str, Any]:
        wrapper = _runtime_wrapper(self.runtime, "_validated_session_state")
        if wrapper is not None:
            return wrapper(state)
        return validated_session_state(state)

    def state_busy_value(self, state: dict[str, Any]) -> bool:
        wrapper = _runtime_wrapper(self.runtime, "_state_busy_value")
        if wrapper is not None:
            return wrapper(state)
        return state_busy_value(state)

    def state_queue_len_value(self, state: dict[str, Any]) -> int:
        wrapper = _runtime_wrapper(self.runtime, "_state_queue_len_value")
        if wrapper is not None:
            return wrapper(state)
        return state_queue_len_value(state)

    def display_session_busy(
        self,
        manager: Any,
        session_id: str,
        session: Any,
        state: dict[str, Any],
    ) -> tuple[bool, bool]:
        wrapper = _runtime_wrapper(self.runtime, "_display_session_busy")
        if wrapper is not None:
            return wrapper(manager, session_id, session, state)
        return display_session_busy(
            self.runtime,
            manager,
            session_id,
            session,
            state,
        )

    def resolved_session_run_settings(
        self,
        session: Any,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        wrapper = _runtime_wrapper(self.runtime, "_resolved_session_run_settings")
        if wrapper is not None:
            return wrapper(session)
        return resolved_session_run_settings(self.runtime, session)

    def run_settings_from_state(
        self,
        state: dict[str, Any],
    ) -> tuple[str | None, str | None, str | None]:
        wrapper = _runtime_wrapper(self.runtime, "_run_settings_from_state")
        if wrapper is not None:
            return wrapper(state)
        return run_settings_from_state(state)

    def resolved_session_token(
        self,
        session: Any,
        token: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        wrapper = _runtime_wrapper(self.runtime, "_resolved_session_token")
        if wrapper is not None:
            return wrapper(session, token=token)
        return resolved_session_token(self.runtime, session, token=token)


def service(runtime: ServerRuntime) -> SessionDisplayService:
    return SessionDisplayService(runtime)


def session_supports_live_pi_ui(session: Any) -> bool:
    if session.backend != "pi":
        return False
    transport = (session.transport or "").strip().lower()
    if transport != "pi-rpc":
        return False
    if session.supports_live_ui is not True:
        return False
    if (
        not isinstance(session.ui_protocol_version, int)
        or session.ui_protocol_version < 1
    ):
        return False
    return True


def is_attention_worthy_session_event(event: dict[str, Any]) -> bool:
    if not isinstance(event, dict) or event.get("display") is False:
        return False
    event_type = str(event.get("type") or "").strip()
    return bool(
        event.get("role") in {"user", "assistant"}
        or bool(event.get("is_error"))
        or event_type == "ask_user"
    )


def attention_updated_ts_from_events(events: list[dict[str, Any]]) -> float | None:
    latest_ts: float | None = None
    for event in events:
        if not is_attention_worthy_session_event(event):
            continue
        ts = event.get("ts")
        if not isinstance(ts, (int, float)) or not math.isfinite(float(ts)):
            continue
        latest_ts = float(ts) if latest_ts is None else max(latest_ts, float(ts))
    return latest_ts


def last_attention_ts_from_pi_tail(
    runtime: Any,
    session_path: Path | None,
    *,
    max_scan_bytes: int = 8 * 1024 * 1024,
) -> float | None:
    if session_path is None or not session_path.exists():
        return None
    try:
        events, _token_update, _off, _scan_bytes, _complete, _diag = (
            runtime.api.pi_messages.read_pi_message_tail_snapshot(
                session_path,
                min_events=80,
                initial_scan_bytes=256 * 1024,
                max_scan_bytes=max_scan_bytes,
            )
        )
    except Exception:
        return None
    if any(is_attention_worthy_session_event(event) for event in events):
        activity_ts = runtime.api.session_file_activity_ts(session_path)
        if activity_ts is not None:
            return activity_ts
    return attention_updated_ts_from_events(events)


def display_updated_ts(session: Any) -> float:
    return (
        float(session.last_chat_ts)
        if isinstance(session.last_chat_ts, (int, float))
        else float(session.start_ts)
    )


def session_row_dedupe_key(runtime: Any, row: dict[str, Any]) -> str:
    if row.get("historical"):
        backend = runtime.api.normalize_agent_backend(
            row.get("agent_backend"),
            default=str(row.get("backend", "codex")),
        )
        return f"historical:{backend}:{str(row.get('session_id', '')).strip()}"
    thread_id = str(row.get("thread_id", "")).strip()
    if thread_id:
        backend = runtime.api.normalize_agent_backend(
            row.get("agent_backend"),
            default=str(row.get("backend", "codex")),
        )
        return f"thread:{backend}:{thread_id}"
    return f"session:{str(row.get('session_id', '')).strip()}"


def display_source_path(session: Any) -> str | None:
    if session.backend == "pi":
        return str(session.session_path) if session.session_path is not None else None
    return str(session.log_path) if session.log_path is not None else None


def durable_session_id_for_live_session(runtime: Any, session: Any) -> str:
    return (
        runtime.api.clean_optional_text(session.thread_id)
        or runtime.api.clean_optional_text(session.session_id)
        or ""
    )


def display_pi_busy(runtime: Any, session: Any, *, broker_busy: bool) -> bool:
    if not broker_busy:
        activity_ts = runtime.api.session_file_activity_ts(session.session_path)
        if activity_ts is not None:
            session.pi_idle_activity_ts = activity_ts
        session.pi_busy_activity_floor = None
        return False
    session_path = session.session_path
    if session_path is None or (not session_path.exists()):
        return True
    activity_ts = runtime.api.session_file_activity_ts(session_path)
    if activity_ts is None:
        return True
    floor = session.pi_busy_activity_floor
    if isinstance(floor, (int, float)) and activity_ts <= float(floor):
        return True
    idle_marker = session.pi_idle_activity_ts
    if isinstance(idle_marker, (int, float)) and activity_ts <= float(idle_marker):
        return False
    idle = runtime.api.pi_messages.is_pi_session_idle(session_path)
    if idle is True:
        session.pi_idle_activity_ts = activity_ts
        session.pi_busy_activity_floor = None
        return False
    if idle is False:
        session.pi_idle_activity_ts = None
    return True


def validated_session_state(state: dict[str, Any] | Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise ValueError("invalid broker state response")
    state_busy_value(state)
    state_queue_len_value(state)
    return state


def state_busy_value(state: dict[str, Any]) -> bool:
    busy_raw = state.get("busy")
    if not isinstance(busy_raw, bool):
        raise ValueError("invalid busy from broker state response")
    return busy_raw


def state_queue_len_value(state: dict[str, Any]) -> int:
    queue_len_raw = state.get("queue_len")
    if type(queue_len_raw) is not int or int(queue_len_raw) < 0:
        raise ValueError("invalid queue_len from broker state response")
    return int(queue_len_raw)


def display_session_busy(
    runtime: Any,
    manager: Any,
    session_id: str,
    session: Any,
    state: dict[str, Any],
) -> tuple[bool, bool]:
    broker_busy = state_busy_value(state)
    busy = (
        display_pi_busy(runtime, session, broker_busy=broker_busy)
        if session.backend == "pi"
        else broker_busy
    )
    if session.backend != "pi" and session.log_path is not None and session.log_path.exists():
        idle_val = manager.idle_from_log(session_id)
        busy = broker_busy or (not bool(idle_val))
    return bool(busy), broker_busy


def resolved_session_run_settings(runtime: Any, session: Any) -> tuple[str | None, str | None, str | None, str | None]:
    model_provider = session.model_provider
    preferred_auth_method = session.preferred_auth_method
    model = session.model
    reasoning_effort = session.reasoning_effort
    if (
        (model_provider is None or model is None or reasoning_effort is None)
        and session.backend == "pi"
        and session.session_path is not None
        and session.session_path.exists()
    ):
        pi_provider, pi_model, pi_effort = runtime.api.read_pi_run_settings(session.session_path)
        if model_provider is None:
            model_provider = pi_provider
        if model is None:
            model = pi_model
        if reasoning_effort is None:
            reasoning_effort = pi_effort
    if (
        (model_provider is None or model is None or reasoning_effort is None)
        and session.log_path is not None
        and session.log_path.exists()
    ):
        log_provider, log_model, log_effort = runtime.api.session_settings.service(runtime).read_run_settings_from_log(
            session.log_path,
            agent_backend=session.agent_backend,
        )
        if model_provider is None:
            model_provider = log_provider
        if model is None:
            model = log_model
        if reasoning_effort is None:
            reasoning_effort = log_effort
    return model_provider, preferred_auth_method, model, reasoning_effort


def run_settings_from_state(
    state: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    provider = state.get("provider")
    if not isinstance(provider, str):
        provider = state.get("modelProvider")
    if not isinstance(provider, str):
        provider = None
    model = state.get("model")
    if not isinstance(model, str):
        model = state.get("modelId")
    if not isinstance(model, str):
        model = None
    reasoning_effort = state.get("reasoning_effort")
    if not isinstance(reasoning_effort, str):
        reasoning_effort = state.get("thinkingLevel")
    if not isinstance(reasoning_effort, str):
        reasoning_effort = None
    return provider, model, reasoning_effort


def resolved_session_token(
    runtime: Any,
    session: Any,
    token: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if isinstance(token, dict):
        return token
    if isinstance(session.token, dict):
        return session.token
    source_path: Path | None = None
    if session.backend == "pi" and session.session_path is not None and session.session_path.exists():
        source_path = session.session_path
    elif session.log_path is not None and session.log_path.exists():
        source_path = session.log_path
    if source_path is None:
        return None
    token_update = runtime.api.rollout_log._find_latest_token_update(source_path)
    return token_update if isinstance(token_update, dict) else None
