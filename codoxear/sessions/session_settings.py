from __future__ import annotations

from pathlib import Path
from typing import Any


def turn_context_run_settings(runtime: Any, payload: Any) -> tuple[str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None
    return (
        runtime._clean_optional_text(payload.get("model")),
        runtime._display_reasoning_effort(payload.get("reasoning_effort") or payload.get("effort")),
    )


def read_session_meta(
    runtime: Any,
    log_path: Path,
    *,
    agent_backend: str | None = None,
) -> dict[str, Any]:
    if agent_backend is None:
        try:
            log_path.resolve().relative_to(runtime.PI_SESSIONS_DIR.resolve())
            backend_name = "pi"
        except Exception:
            backend_name = "codex"
    else:
        backend_name = runtime.normalize_agent_backend(agent_backend)
    payload = runtime._read_session_meta_payload_impl(
        log_path,
        agent_backend=backend_name,
        timeout_s=0.0,
    )
    if payload is None:
        raise ValueError(f"missing session metadata in {log_path}")
    return payload


def read_run_settings_from_log(
    runtime: Any,
    log_path: Path,
    *,
    agent_backend: str = "codex",
) -> tuple[str | None, str | None, str | None]:
    backend_name = runtime.normalize_agent_backend(agent_backend)
    if backend_name == "pi":
        return runtime._read_pi_run_settings(log_path)
    meta = read_session_meta(runtime, log_path, agent_backend="codex")
    model_provider = runtime._clean_optional_text(meta.get("model_provider"))
    model = runtime._clean_optional_text(meta.get("model"))
    reasoning_effort = runtime._display_reasoning_effort(meta.get("reasoning_effort"))
    if model is None or reasoning_effort is None:
        ctx_model, ctx_effort = turn_context_run_settings(
            runtime,
            runtime._rollout_log._find_latest_turn_context(
                log_path,
                max_scan_bytes=8 * 1024 * 1024,
            ),
        )
        if model is None:
            model = ctx_model
        if reasoning_effort is None:
            reasoning_effort = ctx_effort
    return model_provider, model, reasoning_effort


def normalize_requested_model_provider(
    runtime: Any,
    value: Any,
    *,
    allowed: set[str] | None = None,
) -> str | None:
    provider = runtime._clean_optional_text(value)
    if provider is None:
        return None
    if allowed is not None and provider not in allowed:
        allowed_txt = ", ".join(sorted(allowed))
        raise ValueError(f"model_provider must be one of {allowed_txt}")
    return provider


def normalize_requested_service_tier(runtime: Any, value: Any) -> str | None:
    tier = runtime._clean_optional_text(value)
    if tier is None:
        return None
    if tier not in {"fast", "flex"}:
        raise ValueError("service_tier must be one of fast, flex")
    return tier


def normalize_requested_preferred_auth_method(runtime: Any, value: Any) -> str | None:
    method = runtime._clean_optional_text(value)
    if method is None:
        return None
    if method not in {"chatgpt", "apikey"}:
        raise ValueError("preferred_auth_method must be one of chatgpt, apikey")
    return method


def normalize_requested_backend(raw: Any) -> str:
    if raw is None:
        return "codex"
    if not isinstance(raw, str):
        raise ValueError("backend must be a string")
    backend = raw.strip().lower()
    if not backend:
        return "codex"
    if backend not in {"codex", "pi"}:
        raise ValueError("backend must be one of codex, pi")
    return backend


def provider_choice_for_settings(*, model_provider: str | None, preferred_auth_method: str | None) -> str:
    provider = model_provider or "openai"
    if provider == "openai":
        return "chatgpt" if preferred_auth_method == "chatgpt" else "openai-api"
    return provider


def provider_choice_for_backend(
    *,
    backend: str,
    model_provider: str | None,
    preferred_auth_method: str | None,
) -> str | None:
    if backend == "pi":
        return None
    return provider_choice_for_settings(
        model_provider=model_provider,
        preferred_auth_method=preferred_auth_method,
    )


def metadata_log_path(*, meta: dict[str, Any], backend: str, sock: Path) -> Path | None:
    if backend == "pi":
        return None
    if "log_path" not in meta:
        raise ValueError(f"missing log_path in metadata for socket {sock}")
    if meta.get("log_path") is None:
        return None
    log_path_raw = meta.get("log_path")
    if not isinstance(log_path_raw, str) or (not log_path_raw.strip()):
        raise ValueError(f"invalid log_path in metadata for socket {sock}")
    return Path(log_path_raw)


def metadata_session_path(*, meta: dict[str, Any], backend: str, sock: Path) -> Path | None:
    if backend != "pi":
        return None
    if "session_path" not in meta:
        raise ValueError(f"missing session_path in metadata for socket {sock}")
    session_path_raw = meta.get("session_path")
    if not isinstance(session_path_raw, str) or (not session_path_raw.strip()):
        raise ValueError(f"invalid session_path in metadata for socket {sock}")
    return Path(session_path_raw)


def normalize_requested_reasoning_effort(runtime: Any, value: Any) -> str | None:
    normalized = runtime._display_reasoning_effort(value)
    if normalized is None:
        return None
    if normalized not in {"high", "medium", "low"}:
        raise ValueError("reasoning_effort must be one of high, medium, low")
    return normalized


def normalize_requested_pi_reasoning_effort(runtime: Any, value: Any) -> str | None:
    normalized = runtime._display_pi_reasoning_effort(value)
    if normalized is None:
        return None
    if normalized not in {"high", "medium", "low"}:
        raise ValueError("reasoning_effort must be one of high, medium, low")
    return normalized
