from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..runtime import ServerRuntime


def _runtime_wrapper(runtime: ServerRuntime, name: str) -> Any | None:
    module = getattr(runtime, "module", None)
    if module is None or getattr(module, "RUNTIME", None) is not runtime:
        return None
    wrapper = getattr(module, name, None)
    return wrapper if callable(wrapper) else None


@dataclass(slots=True)
class SessionSettingsService:
    runtime: ServerRuntime

    def turn_context_run_settings(self, payload: Any) -> tuple[str | None, str | None]:
        wrapper = _runtime_wrapper(self.runtime, "_turn_context_run_settings")
        if wrapper is not None:
            return wrapper(payload)
        return turn_context_run_settings(self.runtime, payload)

    def read_session_meta(
        self,
        log_path: Path,
        *,
        agent_backend: str | None = None,
    ) -> dict[str, Any]:
        wrapper = _runtime_wrapper(self.runtime, "_read_session_meta")
        if wrapper is not None:
            return wrapper(log_path, agent_backend=agent_backend)
        return read_session_meta(self.runtime, log_path, agent_backend=agent_backend)

    def read_run_settings_from_log(
        self,
        log_path: Path,
        *,
        agent_backend: str = "codex",
    ) -> tuple[str | None, str | None, str | None]:
        wrapper = _runtime_wrapper(self.runtime, "_read_run_settings_from_log")
        if wrapper is not None:
            return wrapper(log_path, agent_backend=agent_backend)
        return read_run_settings_from_log(
            self.runtime,
            log_path,
            agent_backend=agent_backend,
        )

    def normalize_requested_model(self, value: Any) -> str | None:
        wrapper = _runtime_wrapper(self.runtime, "_normalize_requested_model")
        if wrapper is not None:
            return wrapper(value)
        return normalize_requested_model(self.runtime, value)

    def normalize_requested_model_provider(
        self,
        value: Any,
        *,
        allowed: set[str] | None = None,
    ) -> str | None:
        wrapper = _runtime_wrapper(self.runtime, "_normalize_requested_model_provider")
        if wrapper is not None:
            return wrapper(value, allowed=allowed)
        return normalize_requested_model_provider(
            self.runtime,
            value,
            allowed=allowed,
        )

    def normalize_requested_service_tier(self, value: Any) -> str | None:
        wrapper = _runtime_wrapper(self.runtime, "_normalize_requested_service_tier")
        if wrapper is not None:
            return wrapper(value)
        return normalize_requested_service_tier(self.runtime, value)

    def normalize_requested_preferred_auth_method(self, value: Any) -> str | None:
        wrapper = _runtime_wrapper(self.runtime, "_normalize_requested_preferred_auth_method")
        if wrapper is not None:
            return wrapper(value)
        return normalize_requested_preferred_auth_method(self.runtime, value)

    def normalize_requested_backend(self, raw: Any) -> str:
        wrapper = _runtime_wrapper(self.runtime, "_normalize_requested_backend")
        if wrapper is not None:
            return wrapper(raw)
        return normalize_requested_backend(raw)

    def provider_choice_for_settings(
        self,
        *,
        model_provider: str | None,
        preferred_auth_method: str | None,
    ) -> str:
        wrapper = _runtime_wrapper(self.runtime, "_provider_choice_for_settings")
        if wrapper is not None:
            return wrapper(
                model_provider=model_provider,
                preferred_auth_method=preferred_auth_method,
            )
        return provider_choice_for_settings(
            model_provider=model_provider,
            preferred_auth_method=preferred_auth_method,
        )

    def provider_choice_for_backend(
        self,
        *,
        backend: str,
        model_provider: str | None,
        preferred_auth_method: str | None,
    ) -> str | None:
        wrapper = _runtime_wrapper(self.runtime, "_provider_choice_for_backend")
        if wrapper is not None:
            return wrapper(
                backend=backend,
                model_provider=model_provider,
                preferred_auth_method=preferred_auth_method,
            )
        return provider_choice_for_backend(
            backend=backend,
            model_provider=model_provider,
            preferred_auth_method=preferred_auth_method,
        )

    def metadata_log_path(
        self,
        *,
        meta: dict[str, Any],
        backend: str,
        sock: Path,
    ) -> Path | None:
        wrapper = _runtime_wrapper(self.runtime, "_metadata_log_path")
        if wrapper is not None:
            return wrapper(meta=meta, backend=backend, sock=sock)
        return metadata_log_path(meta=meta, backend=backend, sock=sock)

    def metadata_session_path(
        self,
        *,
        meta: dict[str, Any],
        backend: str,
        sock: Path,
    ) -> Path | None:
        wrapper = _runtime_wrapper(self.runtime, "_metadata_session_path")
        if wrapper is not None:
            return wrapper(meta=meta, backend=backend, sock=sock)
        return metadata_session_path(meta=meta, backend=backend, sock=sock)

    def normalize_requested_reasoning_effort(self, value: Any) -> str | None:
        wrapper = _runtime_wrapper(self.runtime, "_normalize_requested_reasoning_effort")
        if wrapper is not None:
            return wrapper(value)
        return normalize_requested_reasoning_effort(self.runtime, value)

    def normalize_requested_pi_reasoning_effort(self, value: Any) -> str | None:
        wrapper = _runtime_wrapper(self.runtime, "_normalize_requested_pi_reasoning_effort")
        if wrapper is not None:
            return wrapper(value)
        return normalize_requested_pi_reasoning_effort(self.runtime, value)


def service(runtime: ServerRuntime) -> SessionSettingsService:
    return SessionSettingsService(runtime)


def turn_context_run_settings(runtime: Any, payload: Any) -> tuple[str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None
    return (
        runtime.api.clean_optional_text(payload.get("model")),
        runtime.api.display_reasoning_effort(payload.get("reasoning_effort") or payload.get("effort")),
    )


def read_session_meta(
    runtime: Any,
    log_path: Path,
    *,
    agent_backend: str | None = None,
) -> dict[str, Any]:
    if agent_backend is None:
        try:
            log_path.resolve().relative_to(runtime.api.PI_SESSIONS_DIR.resolve())
            backend_name = "pi"
        except Exception:
            backend_name = "codex"
    else:
        backend_name = runtime.api.normalize_agent_backend(agent_backend)
    payload = runtime.api.read_session_meta_payload_impl(
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
    backend_name = runtime.api.normalize_agent_backend(agent_backend)
    if backend_name == "pi":
        return runtime.api.read_pi_run_settings(log_path)
    meta = read_session_meta(runtime, log_path, agent_backend="codex")
    model_provider = runtime.api.clean_optional_text(meta.get("model_provider"))
    model = runtime.api.clean_optional_text(meta.get("model"))
    reasoning_effort = runtime.api.display_reasoning_effort(meta.get("reasoning_effort"))
    if model is None or reasoning_effort is None:
        ctx_model, ctx_effort = turn_context_run_settings(
            runtime,
            runtime.api.rollout_log._find_latest_turn_context(
                log_path,
                max_scan_bytes=8 * 1024 * 1024,
            ),
        )
        if model is None:
            model = ctx_model
        if reasoning_effort is None:
            reasoning_effort = ctx_effort
    return model_provider, model, reasoning_effort


def normalize_requested_model(runtime: Any, value: Any) -> str | None:
    out = runtime.api.clean_optional_text(value)
    if out is None:
        return None
    return None if out.lower() == "default" else out


def normalize_requested_model_provider(
    runtime: Any,
    value: Any,
    *,
    allowed: set[str] | None = None,
) -> str | None:
    provider = runtime.api.clean_optional_text(value)
    if provider is None:
        return None
    if allowed is not None and provider not in allowed:
        allowed_txt = ", ".join(sorted(allowed))
        raise ValueError(f"model_provider must be one of {allowed_txt}")
    return provider


def normalize_requested_service_tier(runtime: Any, value: Any) -> str | None:
    tier = runtime.api.clean_optional_text(value)
    if tier is None:
        return None
    if tier not in {"fast", "flex"}:
        raise ValueError("service_tier must be one of fast, flex")
    return tier


def normalize_requested_preferred_auth_method(runtime: Any, value: Any) -> str | None:
    method = runtime.api.clean_optional_text(value)
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
    normalized = runtime.api.display_reasoning_effort(value)
    if normalized is None:
        return None
    if normalized not in {"high", "medium", "low"}:
        raise ValueError("reasoning_effort must be one of high, medium, low")
    return normalized


def normalize_requested_pi_reasoning_effort(runtime: Any, value: Any) -> str | None:
    normalized = runtime.api.display_pi_reasoning_effort(value)
    if normalized is None:
        return None
    if normalized not in {"high", "medium", "low"}:
        raise ValueError("reasoning_effort must be one of high, medium, low")
    return normalized
