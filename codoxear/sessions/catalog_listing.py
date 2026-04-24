from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..agent_backend import normalize_agent_backend
from ..page_state_sqlite import PageStateDB
from .runtime_access import manager_runtime


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip()
    return out or None


def _active_durable_ids(manager: Any) -> set[str]:
    return {
        (_clean_optional_text(v.thread_id) or _clean_optional_text(v.session_id) or "")
        for v in manager._sessions.values()
    }


def _build_live_item(
    manager: Any,
    sv: Any,
    session: Any,
    *,
    qmap: Any,
    meta_map: Any,
    now_ts: float,
) -> tuple[dict[str, Any], set[tuple[str, str]], bool]:
    live_resume_keys: set[tuple[str, str]] = set()
    sidebar_dirty = False

    thread_id = str(session.thread_id or "").strip()
    if thread_id:
        live_resume_keys.add(
            (
                normalize_agent_backend(session.agent_backend, default=session.backend or "codex"),
                thread_id,
            )
        )

    cfg0 = manager._harness.get(session.session_id)
    h_enabled = bool(cfg0.get("enabled")) if isinstance(cfg0, dict) else False
    h_cooldown_minutes = (
        sv.api.clean_harness_cooldown_minutes(cfg0.get("cooldown_minutes"))
        if isinstance(cfg0, dict)
        else sv.api.HARNESS_DEFAULT_IDLE_MINUTES
    )
    h_remaining_injections = (
        sv.api.clean_harness_remaining_injections(cfg0.get("remaining_injections"), allow_zero=True)
        if isinstance(cfg0, dict)
        else sv.api.HARNESS_DEFAULT_MAX_INJECTIONS
    )

    log_exists = bool(session.log_path is not None and session.log_path.exists())
    if (
        session.model_provider is None
        or session.model is None
        or session.reasoning_effort is None
    ):
        try:
            resolved_provider, _preferred_auth_method, resolved_model, resolved_effort = (
                sv.api.session_display.service(sv).resolved_session_run_settings(session)
            )
        except (FileNotFoundError, ValueError):
            resolved_provider = resolved_model = resolved_effort = None
        if session.model_provider is None:
            session.model_provider = resolved_provider
        if session.model is None:
            session.model = resolved_model
        if session.reasoning_effort is None:
            session.reasoning_effort = resolved_effort

    if session.last_chat_ts is None and log_exists and session.log_path is not None and (not session.last_chat_history_scanned):
        conv_ts = sv.api.last_conversation_ts_from_tail(session.log_path)
        session.last_chat_history_scanned = True
        if isinstance(conv_ts, (int, float)):
            session.last_chat_ts = float(conv_ts)

    if session.backend == "pi" and session.session_path is not None and session.session_path.exists():
        activity_ts = sv.api.session_file_activity_ts(session.session_path)
        scanned_activity_ts = session.pi_attention_scan_activity_ts
        should_refresh_attention = bool(
            activity_ts is not None
            and (
                scanned_activity_ts is None
                or float(activity_ts) > float(scanned_activity_ts)
            )
        )
        if should_refresh_attention or (session.last_chat_ts is None and (not session.last_chat_history_scanned)):
            conv_ts = sv.api.session_display.service(sv).last_attention_ts_from_pi_tail(session.session_path)
            session.last_chat_history_scanned = True
            session.pi_attention_scan_activity_ts = activity_ts
            if isinstance(conv_ts, (int, float)):
                session.last_chat_ts = (
                    float(conv_ts)
                    if session.last_chat_ts is None
                    else max(float(session.last_chat_ts), float(conv_ts))
                )

    updated_ts = sv.api.session_display.service(sv).display_updated_ts(session)
    canonical_cwd = sv.api.canonical_session_cwd(session.cwd)
    cwd_recent = sv.api.clean_recent_cwd(canonical_cwd)
    recent_map = getattr(manager, "_recent_cwds", None)
    if cwd_recent is not None:
        if not isinstance(recent_map, dict):
            manager._recent_cwds = {}
            recent_map = manager._recent_cwds
        prev_recent_ts = recent_map.get(cwd_recent)
        if prev_recent_ts is None or prev_recent_ts < updated_ts:
            recent_map[cwd_recent] = updated_ts

    ref = manager.page_state_ref_for_session(session)
    queue_len = 0
    if isinstance(qmap, dict):
        q0 = qmap.get(session.session_id)
        if not isinstance(q0, list) and ref is not None:
            q0 = qmap.get(ref)
        if isinstance(q0, list):
            queue_len = len(q0)

    meta0 = None
    if isinstance(meta_map, dict):
        meta0 = meta_map.get(session.session_id)
        if meta0 is None and ref is not None:
            meta0 = meta_map.get(ref)
    if not isinstance(meta0, dict):
        meta0 = {}

    priority_offset = sv.api.clean_priority_offset(meta0.get("priority_offset"))
    snooze_until = sv.api.clean_snooze_until(meta0.get("snooze_until"))
    dependency_session_id = sv.api.clean_dependency_session_id(meta0.get("dependency_session_id"))

    active_durable_ids = _active_durable_ids(manager)
    this_durable_id = _clean_optional_text(session.thread_id) or _clean_optional_text(session.session_id)
    if dependency_session_id == this_durable_id or (
        dependency_session_id is not None and dependency_session_id not in active_durable_ids
    ):
        dependency_session_id = None
        if isinstance(meta_map, dict) and isinstance(meta0, dict):
            meta0.pop("dependency_session_id", None)
            sidebar_dirty = True

    if snooze_until is not None and snooze_until <= now_ts:
        snooze_until = None
        if isinstance(meta_map, dict) and isinstance(meta0, dict):
            meta0.pop("snooze_until", None)
            sidebar_dirty = True

    elapsed_s = max(0.0, now_ts - updated_ts)
    time_priority = sv.api.priority_from_elapsed_seconds(elapsed_s)
    base_priority = sv.api.clip01(time_priority + priority_offset)
    blocked = dependency_session_id is not None
    snoozed = snooze_until is not None and snooze_until > now_ts
    final_priority = 0.0 if (snoozed or blocked) else base_priority

    cwd_path = sv.api.safe_expanduser(Path(canonical_cwd or session.cwd))
    if not cwd_path.is_absolute():
        cwd_path = cwd_path.resolve()
    git_branch = sv.api.current_git_branch(cwd_path)

    if not session.title:
        try:
            if ref is not None:
                record = manager.catalog_record_for_ref(ref)
                record_title = sv.api.clean_optional_text(
                    getattr(record, "title", None)
                )
                if record_title:
                    session.title = record_title
            if (
                not session.title
                and session.backend == "pi"
                and session.session_path is not None
                and session.session_path.exists()
            ):
                title = sv.api.pi_session_files.service(sv).pi_session_name_from_session_file(
                    session.session_path
                )
                if title:
                    session.title = title
        except Exception:
            pass

    if session.first_user_message is None:
        try:
            preview = ""
            if session.backend == "pi" and session.session_path is not None and session.session_path.exists():
                preview = sv.api.session_listing.service(sv).first_user_message_preview_from_pi_session(session.session_path)
            elif log_exists and session.log_path is not None:
                preview = sv.api.session_listing.service(sv).first_user_message_preview_from_log(session.log_path)
            if preview:
                session.first_user_message = preview
        except Exception:
            pass

    durable_session_id = ref[1] if ref is not None else manager.durable_session_id_for_session(session)
    if not session.title:
        try:
            record_ref = ref if ref is not None else (session.backend, durable_session_id)
            if record_ref is not None:
                record = manager.catalog_record_for_ref(record_ref)
                record_title = sv.api.clean_optional_text(
                    getattr(record, "title", None)
                )
                if record_title:
                    session.title = record_title
        except Exception:
            pass
    row = {
        "session_id": durable_session_id,
        "runtime_id": session.session_id,
        "thread_id": session.thread_id,
        "backend": session.backend,
        "pid": session.codex_pid,
        "broker_pid": session.broker_pid,
        "agent_backend": session.agent_backend,
        "owned": session.owned,
        "transport": session.transport,
        "cwd": canonical_cwd,
        "start_ts": session.start_ts,
        "updated_ts": updated_ts,
        "log_path": str(session.log_path) if session.log_path is not None else None,
        "log_exists": log_exists,
        "state_busy": bool(session.busy),
        "queue_len": int(queue_len),
        "token": session.token,
        "thinking": int(session.meta_thinking),
        "tools": int(session.meta_tools),
        "system": int(session.meta_system),
        "harness_enabled": h_enabled,
        "harness_cooldown_minutes": h_cooldown_minutes,
        "harness_remaining_injections": h_remaining_injections,
        "alias": (
            manager._aliases.get(session.session_id)
            if manager._aliases.get(session.session_id) is not None
            else (manager._aliases.get(ref) if ref is not None else None)
        ),
        "title": session.title or "",
        "first_user_message": session.first_user_message or "",
        "files": (
            list(manager._files.get(session.session_id, manager._files.get(ref, [])))
            if ref is not None
            else list(manager._files.get(session.session_id, []))
        ),
        "git_branch": git_branch,
        "model_provider": session.model_provider,
        "preferred_auth_method": session.preferred_auth_method,
        "provider_choice": sv.api.session_settings.service(sv).provider_choice_for_backend(
            backend=session.backend,
            model_provider=session.model_provider,
            preferred_auth_method=session.preferred_auth_method,
        ),
        "model": session.model,
        "reasoning_effort": session.reasoning_effort,
        "service_tier": session.service_tier,
        "tmux_session": session.tmux_session,
        "tmux_window": session.tmux_window,
        "priority_offset": priority_offset,
        "snooze_until": snooze_until,
        "dependency_session_id": dependency_session_id,
        "time_priority": time_priority,
        "base_priority": base_priority,
        "final_priority": final_priority,
        "blocked": blocked,
        "snoozed": snoozed,
        "focused": bool(meta0.get("focused")),
    }
    return row, live_resume_keys, sidebar_dirty


def _collect_live_items(
    manager: Any,
    sv: Any,
    *,
    qmap: Any,
    meta_map: Any,
    now_ts: float,
) -> tuple[list[dict[str, Any]], set[tuple[str, str]], bool]:
    items: list[dict[str, Any]] = []
    live_resume_keys: set[tuple[str, str]] = set()
    sidebar_dirty = False
    for session in manager._sessions.values():
        row, row_keys, row_sidebar_dirty = _build_live_item(
            manager,
            sv,
            session,
            qmap=qmap,
            meta_map=meta_map,
            now_ts=now_ts,
        )
        items.append(row)
        live_resume_keys.update(row_keys)
        sidebar_dirty = bool(sidebar_dirty or row_sidebar_dirty)
    return items, live_resume_keys, sidebar_dirty


def _collect_recovered_catalog_items(
    manager: Any,
    sv: Any,
    *,
    recovered_catalog: dict[Any, Any],
    live_resume_keys: set[tuple[str, str]],
    hidden_sessions: set[str],
    meta_map: Any,
    active_durable_ids: set[str],
    now_ts: float,
) -> tuple[list[dict[str, Any]], bool]:
    items: list[dict[str, Any]] = []
    sidebar_dirty = False
    for ref, record in recovered_catalog.items():
        backend, durable_session_id = ref
        if backend != "pi":
            continue
        if (backend, durable_session_id) in live_resume_keys:
            continue

        session_row_id = durable_session_id if record.pending_startup else sv.api.session_listing.service(sv).historical_session_id(backend, durable_session_id)
        if hidden_sessions.intersection(
            manager.hidden_session_keys(
                session_row_id,
                durable_session_id,
                durable_session_id,
                backend,
            )
        ):
            continue

        meta0 = meta_map.get(ref) if isinstance(meta_map, dict) else None
        if not isinstance(meta0, dict):
            meta0 = {}
        priority_offset = sv.api.clean_priority_offset(meta0.get("priority_offset"))
        snooze_until = sv.api.clean_snooze_until(meta0.get("snooze_until"))
        dependency_session_id = sv.api.clean_dependency_session_id(meta0.get("dependency_session_id"))
        if dependency_session_id is not None and dependency_session_id not in active_durable_ids:
            dependency_session_id = None
            if isinstance(meta_map, dict):
                meta0.pop("dependency_session_id", None)
                sidebar_dirty = True
        if snooze_until is not None and snooze_until <= now_ts:
            snooze_until = None
            if isinstance(meta_map, dict):
                meta0.pop("snooze_until", None)
                sidebar_dirty = True

        updated_ts = float(record.updated_at or record.created_at or now_ts)
        elapsed_s = max(0.0, now_ts - updated_ts)
        time_priority = sv.api.priority_from_elapsed_seconds(elapsed_s)
        base_priority = sv.api.clip01(time_priority + priority_offset)
        blocked = dependency_session_id is not None
        snoozed = snooze_until is not None and snooze_until > now_ts
        final_priority = 0.0 if (snoozed or blocked) else base_priority

        alias = manager._aliases.get(ref) if isinstance(manager._aliases, dict) else None
        queue_rows = manager._queues.get(ref, []) if isinstance(manager._queues, dict) else []
        file_rows = manager._files.get(ref, []) if isinstance(manager._files, dict) else []
        cwd = record.cwd or ""
        history_cwd_path: Path | None = sv.api.safe_expanduser(Path(cwd)).resolve() if cwd else None
        git_branch = sv.api.current_git_branch(history_cwd_path) if history_cwd_path is not None else None
        source_path_raw = record.source_path or ""
        source_path = Path(source_path_raw) if source_path_raw else None
        model_provider = model = reasoning_effort = None
        if source_path is not None and source_path.exists():
            try:
                model_provider, model, reasoning_effort = sv.api.read_pi_run_settings(
                    source_path
                )
            except Exception:
                model_provider = model = reasoning_effort = None

        items.append(
            {
                "session_id": session_row_id,
                "runtime_id": None,
                "thread_id": durable_session_id,
                "resume_session_id": durable_session_id,
                "backend": backend,
                "pid": None,
                "broker_pid": None,
                "agent_backend": backend,
                "owned": False,
                "transport": None,
                "cwd": cwd,
                "start_ts": float(record.created_at or updated_ts),
                "updated_ts": updated_ts,
                "busy": False,
                "queue_len": len(queue_rows) if isinstance(queue_rows, list) else 0,
                "token": None,
                "thinking": 0,
                "tools": 0,
                "system": 0,
                "harness_enabled": False,
                "harness_cooldown_minutes": sv.api.HARNESS_DEFAULT_IDLE_MINUTES,
                "harness_remaining_injections": sv.api.HARNESS_DEFAULT_MAX_INJECTIONS,
                "alias": alias,
                "title": record.title or "",
                "first_user_message": record.first_user_message or "",
                "focused": bool(meta0.get("focused")),
                "files": list(file_rows) if isinstance(file_rows, list) else [],
                "git_branch": git_branch,
                "model_provider": model_provider,
                "preferred_auth_method": None,
                "provider_choice": sv.api.session_settings.service(sv).provider_choice_for_backend(
                    backend=backend,
                    model_provider=model_provider,
                    preferred_auth_method=None,
                ),
                "model": model,
                "reasoning_effort": reasoning_effort,
                "service_tier": None,
                "tmux_session": None,
                "tmux_window": None,
                "priority_offset": priority_offset,
                "snooze_until": snooze_until,
                "dependency_session_id": dependency_session_id,
                "time_priority": time_priority,
                "base_priority": base_priority,
                "final_priority": final_priority,
                "blocked": blocked,
                "snoozed": snoozed,
                "historical": not record.pending_startup,
                "pending_startup": bool(record.pending_startup),
                "source_path": record.source_path,
                "session_path": record.source_path,
            }
        )
    return items, sidebar_dirty


def _build_output_rows(manager: Any, sv: Any, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items:
        sid = str(it["session_id"])
        agent_backend = normalize_agent_backend(it.get("agent_backend"), default="codex")
        if it.get("historical"):
            out.append(sv.api.session_listing.service(sv).normalize_session_cwd_row(dict(it)))
            continue

        log_exists = bool(it.get("log_exists"))
        state_busy = bool(it.get("state_busy"))
        if not log_exists and it.get("backend") == "pi":
            s_obj = manager._sessions.get(sid)
            busy_out = sv.api.session_display.service(sv).display_pi_busy(s_obj, broker_busy=state_busy) if s_obj is not None else state_busy
        elif not log_exists:
            busy_out = False
        else:
            idle_val = bool(manager.idle_from_log(sid))
            if agent_backend == "pi":
                busy_out = not idle_val
            else:
                busy_out = state_busy or (not idle_val)

        it2 = dict(it)
        it2.pop("log_exists", None)
        it2.pop("state_busy", None)
        it2["busy"] = bool(busy_out)
        out.append(sv.api.session_listing.service(sv).normalize_session_cwd_row(it2))

    return out


def _sort_and_dedupe_rows(sv: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows.sort(
        key=lambda item: (
            -float(item.get("final_priority", 0.0)),
            -float(item.get("updated_ts", item.get("start_ts", 0.0))),
            -float(item.get("start_ts", 0.0)),
            0 if normalize_agent_backend(item.get("agent_backend"), default="codex") == "pi" else 1,
            str(item.get("session_id", "")),
        )
    )

    deduped: list[dict[str, Any]] = []
    seen_row_keys: set[str] = set()
    for item in rows:
        row_key = sv.api.session_display.service(sv).session_row_dedupe_key(item)
        if row_key in seen_row_keys:
            continue
        seen_row_keys.add(row_key)
        deduped.append(item)
    return deduped


def list_sessions(manager: Any) -> list[dict[str, Any]]:
    sv = manager_runtime(manager)
    recovered_catalog: dict[Any, Any] = {}
    db = getattr(manager, "_page_state_db", None)
    if isinstance(db, PageStateDB):
        recovered_catalog = db.load_sessions()

    if float(getattr(manager, "_last_discover_ts", 0.0) or 0.0) <= 0.0:
        manager.discover_existing_if_stale(force=True)
    manager.update_meta_counters()

    sidebar_dirty = False
    now_ts = time.time()

    with manager._lock:
        qmap = getattr(manager, "_queues", None)
        meta_map = getattr(manager, "_sidebar_meta", None)
        hidden_sessions = set(getattr(manager, "_hidden_sessions", set()))
        active_durable_ids = _active_durable_ids(manager)

        items, live_resume_keys, live_sidebar_dirty = _collect_live_items(
            manager,
            sv,
            qmap=qmap,
            meta_map=meta_map,
            now_ts=now_ts,
        )
        sidebar_dirty = bool(sidebar_dirty or live_sidebar_dirty)

        recovered_items, recovered_sidebar_dirty = _collect_recovered_catalog_items(
            manager,
            sv,
            recovered_catalog=recovered_catalog,
            live_resume_keys=live_resume_keys,
            hidden_sessions=hidden_sessions,
            meta_map=meta_map,
            active_durable_ids=active_durable_ids,
            now_ts=now_ts,
        )
        items.extend(recovered_items)
        sidebar_dirty = bool(sidebar_dirty or recovered_sidebar_dirty)

        if bool(getattr(manager, "_include_historical_sessions", False)):
            for hist in sv.api.session_listing.service(sv).historical_sidebar_items(live_resume_keys=live_resume_keys, now_ts=now_ts):
                if hidden_sessions.intersection(
                    manager.hidden_session_keys(
                        hist.get("session_id"),
                        hist.get("thread_id"),
                        hist.get("resume_session_id"),
                        hist.get("agent_backend"),
                    )
                ):
                    continue
                items.append(hist)

    out = _build_output_rows(manager, sv, items)

    for item in out:
        if item.get("busy") or int(item.get("queue_len", 0)) <= 0:
            continue
        manager.maybe_drain_session_queue(str(item["session_id"]))

    if sidebar_dirty:
        manager.save_sidebar_meta()

    return _sort_and_dedupe_rows(sv, out)
