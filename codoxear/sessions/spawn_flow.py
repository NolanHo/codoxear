from __future__ import annotations

from pathlib import Path
from typing import Any

from ..agent_backend import normalize_agent_backend
from .runtime_access import manager_runtime


def spawn_web_session(
    manager: Any,
    *,
    cwd: str,
    args: list[str] | None = None,
    agent_backend: str = "codex",
    resume_session_id: str | None = None,
    worktree_branch: str | None = None,
    model_provider: str | None = None,
    preferred_auth_method: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
    create_in_tmux: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    sv = manager_runtime(manager)

    backend_name = normalize_agent_backend(
        backend, default=normalize_agent_backend(agent_backend, default="codex")
    )
    cwd_path = sv.api.resolve_dir_target(cwd, field_name="cwd")
    if not cwd_path.exists():
        try:
            cwd_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            detail = exc.strerror or str(exc)
            raise ValueError(f"cwd could not be created: {cwd_path}: {detail}") from exc
    if not cwd_path.is_dir():
        raise ValueError(f"cwd is not a directory: {cwd_path}")
    cwd3 = str(cwd_path)
    if backend_name == "pi":
        spawn_nonce = sv.api.secrets.token_hex(8)
        pending_session_id: str | None = None
        pending_delete_on_failure = True
        pending_restore_record: Any | None = None
        if resume_session_id is not None:
            resume_id = sv.api.clean_optional_resume_session_id(resume_session_id)
            if not resume_id:
                raise ValueError("resume_session_id must be a non-empty string")
            session_path: Path | None = None
            for row in sv.api.resume_candidates.service(sv).list_resume_candidates_for_cwd(cwd3, limit=1000, backend="pi"):
                if row.get("session_id") != resume_id:
                    continue
                raw_session_path = row.get("session_path")
                if isinstance(raw_session_path, str) and raw_session_path:
                    session_path = Path(raw_session_path)
                    break
            if session_path is None:
                raise ValueError(f"resume session not found for cwd: {resume_id}")
            if create_in_tmux:
                pending_session_id = resume_id
                pending_delete_on_failure = False
                db = getattr(manager, "_page_state_db", None)
                pending_restore_record = (
                    db.load_sessions().get(("pi", resume_id)) if isinstance(db, sv.api.PageStateDB) else None
                )
                current = pending_restore_record
                manager.persist_durable_session_record(
                    sv.api.DurableSessionRecord(
                        backend="pi",
                        session_id=resume_id,
                        cwd=(current.cwd if current is not None else cwd3),
                        source_path=(current.source_path if current is not None else str(session_path)),
                        title=current.title if current is not None else None,
                        first_user_message=current.first_user_message if current is not None else None,
                        created_at=(current.created_at if current is not None else sv.api.safe_path_mtime(session_path)),
                        updated_at=(current.updated_at if current is not None else sv.api.safe_path_mtime(session_path)),
                        pending_startup=True,
                    )
                )
        else:
            pending_session_id = str(sv.api.uuid.uuid4())
            session_path = sv.api.pi_new_session_file_for_cwd(cwd_path)
            sv.api.pi_session_files.service(sv).write_pi_session_header(
                session_path,
                session_id=pending_session_id,
                cwd=cwd3,
                provider=model_provider,
                model_id=model,
                thinking_level=reasoning_effort,
            )
            manager.persist_durable_session_record(
                sv.api.DurableSessionRecord(
                    backend="pi",
                    session_id=pending_session_id,
                    cwd=cwd3,
                    source_path=str(session_path),
                    created_at=sv.api.safe_path_mtime(session_path),
                    updated_at=sv.api.safe_path_mtime(session_path),
                    pending_startup=True,
                )
            )
        session_path.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            sv.api.sys.executable,
            "-m",
            "codoxear.pi_broker",
            "--cwd",
            str(cwd_path),
            "--session-file",
            str(session_path),
            "--",
            "-e",
            str(Path(sv.api.__file__).resolve().parent / "pi_extensions" / "ask_user_bridge.ts"),
        ]
        env = dict(sv.api.os.environ)
        if sv.api.DOTENV.exists():
            for key, value in sv.api.load_env_file(sv.api.DOTENV).items():
                env.setdefault(key, value)
        env["CODEX_WEB_OWNER"] = "web"
        env["CODEX_WEB_SPAWN_NONCE"] = spawn_nonce
        env.setdefault("PI_HOME", str(sv.api.PI_HOME))
        if create_in_tmux:
            tmux_bin = sv.api.shutil.which("tmux")
            if tmux_bin is None:
                if pending_session_id is not None and pending_delete_on_failure:
                    manager.delete_durable_session_record(("pi", pending_session_id))
                elif pending_restore_record is not None:
                    manager.persist_durable_session_record(pending_restore_record)
                raise ValueError("tmux is unavailable on this host")
            tmux_window = sv.api.safe_filename(f"{Path(cwd3).name or 'session'}-{spawn_nonce[:6]}", default="session")
            env["CODEX_WEB_TRANSPORT"] = "tmux"
            env["CODEX_WEB_TMUX_SESSION"] = sv.api.TMUX_SESSION_NAME
            env["CODEX_WEB_TMUX_WINDOW"] = tmux_window
            short_app_dir = sv.api.spawn_utils.service(sv).ensure_tmux_short_app_dir()
            inline_env = {
                "CODEX_WEB_OWNER": "web",
                "CODEX_WEB_AGENT_BACKEND": "pi",
                "CODEX_WEB_TRANSPORT": "tmux",
                "CODEX_WEB_TMUX_SESSION": sv.api.TMUX_SESSION_NAME,
                "CODEX_WEB_TMUX_WINDOW": tmux_window,
                "CODEX_WEB_SPAWN_NONCE": spawn_nonce,
                "CODOXEAR_APP_DIR": short_app_dir,
                "PI_HOME": str(env["PI_HOME"]),
            }
            repo_root = Path(sv.api.__file__).resolve().parent.parent
            inline_argv = ["env", *[f"{key}={value}" for key, value in inline_env.items()], *argv]
            shell_cmd = f"cd {sv.api.shlex.quote(str(repo_root))} && exec {sv.api.shlex.join(inline_argv)}"
            has_session = sv.api.subprocess.run(
                [tmux_bin, "has-session", "-t", sv.api.TMUX_SESSION_NAME],
                stdout=sv.api.subprocess.DEVNULL,
                stderr=sv.api.subprocess.DEVNULL,
                text=True,
                check=False,
            )
            if has_session.returncode == 0:
                tmux_argv = [
                    tmux_bin,
                    "new-window",
                    "-d",
                    "-P",
                    "-F",
                    "#{pane_id}",
                    "-t",
                    f"{sv.api.TMUX_SESSION_NAME}:",
                    "-n",
                    tmux_window,
                    shell_cmd,
                ]
            else:
                tmux_argv = [
                    tmux_bin,
                    "new-session",
                    "-d",
                    "-P",
                    "-F",
                    "#{pane_id}",
                    "-s",
                    sv.api.TMUX_SESSION_NAME,
                    "-n",
                    tmux_window,
                    shell_cmd,
                ]
            tmux_proc = sv.api.subprocess.run(tmux_argv, capture_output=True, text=True, env=env, check=False)
            if tmux_proc.returncode != 0:
                if pending_session_id is not None and pending_delete_on_failure:
                    manager.delete_durable_session_record(("pi", pending_session_id))
                elif pending_restore_record is not None:
                    manager.persist_durable_session_record(pending_restore_record)
                detail = (tmux_proc.stderr or tmux_proc.stdout or f"exit status {tmux_proc.returncode}").strip()
                raise RuntimeError(f"tmux launch failed: {detail}")
            if pending_session_id is not None:
                sv.api.threading.Thread(
                    target=manager.finalize_pending_pi_spawn,
                    kwargs={
                        "spawn_nonce": spawn_nonce,
                        "durable_session_id": pending_session_id,
                        "cwd": cwd3,
                        "session_path": session_path,
                        "proc": None,
                        "delete_on_failure": pending_delete_on_failure,
                        "restore_record_on_failure": pending_restore_record,
                    },
                    daemon=True,
                ).start()
                return {
                    "session_id": pending_session_id,
                    "runtime_id": None,
                    "backend": "pi",
                    "pending_startup": True,
                    "tmux_session": sv.api.TMUX_SESSION_NAME,
                    "tmux_window": tmux_window,
                }
            meta = sv.api.spawn_utils.service(sv).wait_for_spawned_broker_meta(spawn_nonce)
            payload = sv.api.spawn_utils.service(sv).spawn_result_from_meta(meta)
            return {**payload, "tmux_session": sv.api.TMUX_SESSION_NAME, "tmux_window": tmux_window}
        try:
            proc = sv.api.subprocess.Popen(
                argv,
                stdin=sv.api.subprocess.DEVNULL,
                stdout=sv.api.subprocess.DEVNULL,
                stderr=sv.api.subprocess.PIPE,
                env=env,
                start_new_session=True,
            )
        except Exception as exc:
            if pending_session_id is not None and pending_delete_on_failure:
                manager.delete_durable_session_record(("pi", pending_session_id))
            elif pending_restore_record is not None:
                manager.persist_durable_session_record(pending_restore_record)
            raise RuntimeError(f"spawn failed: {exc}") from exc
        sv.api.threading.Thread(target=proc.wait, daemon=True).start()
        if pending_session_id is not None:
            sv.api.threading.Thread(
                target=manager.finalize_pending_pi_spawn,
                kwargs={
                    "spawn_nonce": spawn_nonce,
                    "durable_session_id": pending_session_id,
                    "cwd": cwd3,
                    "session_path": session_path,
                    "proc": proc,
                    "delete_on_failure": pending_delete_on_failure,
                    "restore_record_on_failure": pending_restore_record,
                },
                daemon=True,
            ).start()
            payload = {
                "session_id": pending_session_id,
                "runtime_id": None,
                "backend": "pi",
                "pending_startup": True,
            }
            sv.api.event_publish.service(sv).publish_sessions_invalidate(reason="session_created")
            return payload
        sv.api.spawn_utils.service(sv).wait_or_raise(proc, label="pi broker", timeout_s=1.5)
        sv.api.start_proc_stderr_drain(proc)
        meta = sv.api.spawn_utils.service(sv).wait_for_spawned_broker_meta(spawn_nonce)
        payload = sv.api.spawn_utils.service(sv).spawn_result_from_meta(meta)
        sv.api.event_publish.service(sv).publish_sessions_invalidate(reason="session_created")
        return payload

    if resume_session_id is not None and worktree_branch is not None:
        raise ValueError("worktree_branch cannot be used when resuming a session")
    spawn_cwd = cwd_path
    if worktree_branch is not None:
        spawn_cwd = sv.api.spawn_utils.service(sv).create_git_worktree(cwd_path, worktree_branch)

    argv = [sv.api.sys.executable, "-m", "codoxear.broker", "--cwd", str(spawn_cwd), "--"]
    codex_args: list[str] = []
    resume_row: dict[str, Any] | None = None
    if backend_name == "codex":
        codex_args = [
            "-c",
            sv.api.codex_trust_override_for_path(spawn_cwd),
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        if model is not None:
            codex_args.extend(["--model", model])
        if reasoning_effort is not None:
            codex_args.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
        if model_provider is not None:
            codex_args.extend(["-c", f'model_provider="{model_provider}"'])
        if preferred_auth_method is not None:
            codex_args.extend(["-c", f'preferred_auth_method="{preferred_auth_method}"'])
        if service_tier is not None:
            codex_args.extend(["-c", f'service_tier="{service_tier}"'])
    else:
        if preferred_auth_method is not None:
            raise ValueError("preferred_auth_method is not supported for pi")
        if service_tier is not None:
            raise ValueError("service_tier is not supported for pi")
        if model_provider is not None:
            codex_args.extend(["--provider", model_provider])
        if model is not None:
            codex_args.extend(["--model", model])
        if reasoning_effort is not None:
            codex_args.extend(["--thinking", reasoning_effort])
    if resume_session_id is not None:
        resume_id = sv.api.clean_optional_resume_session_id(resume_session_id)
        if not resume_id:
            raise ValueError("resume_session_id must be a non-empty string")
        found = False
        for row in sv.api.resume_candidates.service(sv).list_resume_candidates_for_cwd(cwd3, agent_backend=backend_name, limit=1000):
            if row.get("session_id") == resume_id:
                found = True
                resume_row = row
                break
        if not found:
            raise ValueError(f"resume session not found for cwd: {resume_id}")
        if backend_name == "codex":
            codex_args.extend(["resume", resume_id])
        else:
            resume_target = str(resume_row.get("log_path") or "").strip() if isinstance(resume_row, dict) else ""
            codex_args.extend(["--session", resume_target or resume_id])
    codex_args.extend(args or [])
    argv.extend(codex_args)

    env = dict(sv.api.os.environ)
    if sv.api.DOTENV.exists():
        for key, value in sv.api.load_env_file(sv.api.DOTENV).items():
            env.setdefault(key, value)
    env["CODEX_WEB_OWNER"] = "web"
    env["CODEX_WEB_AGENT_BACKEND"] = backend_name
    if backend_name == "codex":
        env.setdefault("CODEX_HOME", str(sv.api.CODEX_HOME))
        env.pop("PI_HOME", None)
    else:
        env.setdefault("PI_HOME", str(sv.api.PI_HOME))
        env.pop("CODEX_HOME", None)
    env.pop("CODEX_WEB_MODEL_PROVIDER", None)
    env.pop("CODEX_WEB_PREFERRED_AUTH_METHOD", None)
    env.pop("CODEX_WEB_MODEL", None)
    env.pop("CODEX_WEB_REASONING_EFFORT", None)
    env.pop("CODEX_WEB_SERVICE_TIER", None)
    env.pop("CODEX_WEB_TRANSPORT", None)
    env.pop("CODEX_WEB_TMUX_SESSION", None)
    env.pop("CODEX_WEB_TMUX_WINDOW", None)
    env.pop("CODEX_WEB_SPAWN_NONCE", None)
    env.pop("CODEX_WEB_RESUME_SESSION_ID", None)
    env.pop("CODEX_WEB_RESUME_LOG_PATH", None)
    spawn_nonce = sv.api.secrets.token_hex(8)
    env["CODEX_WEB_SPAWN_NONCE"] = spawn_nonce
    if model_provider is not None:
        env["CODEX_WEB_MODEL_PROVIDER"] = model_provider
    if preferred_auth_method is not None:
        env["CODEX_WEB_PREFERRED_AUTH_METHOD"] = preferred_auth_method
    if model is not None:
        env["CODEX_WEB_MODEL"] = model
    if reasoning_effort is not None:
        env["CODEX_WEB_REASONING_EFFORT"] = reasoning_effort
    if service_tier is not None:
        env["CODEX_WEB_SERVICE_TIER"] = service_tier
    if resume_session_id is not None:
        env["CODEX_WEB_RESUME_SESSION_ID"] = resume_session_id
    if create_in_tmux:
        tmux_bin = sv.api.shutil.which("tmux")
        if tmux_bin is None:
            raise ValueError("tmux is unavailable on this host")
        tmux_window = sv.api.safe_filename(f"{Path(spawn_cwd).name or 'session'}-{spawn_nonce[:6]}", default="session")
        env["CODEX_WEB_TRANSPORT"] = "tmux"
        env["CODEX_WEB_TMUX_SESSION"] = sv.api.TMUX_SESSION_NAME
        env["CODEX_WEB_TMUX_WINDOW"] = tmux_window
        env["CODEX_WEB_SPAWN_NONCE"] = spawn_nonce
        short_app_dir = sv.api.spawn_utils.service(sv).ensure_tmux_short_app_dir()
        inline_env = {
            "CODEX_WEB_OWNER": "web",
            "CODEX_WEB_AGENT_BACKEND": backend_name,
            "CODEX_WEB_TRANSPORT": "tmux",
            "CODEX_WEB_TMUX_SESSION": sv.api.TMUX_SESSION_NAME,
            "CODEX_WEB_TMUX_WINDOW": tmux_window,
            "CODEX_WEB_SPAWN_NONCE": spawn_nonce,
            "CODOXEAR_APP_DIR": short_app_dir,
        }
        if backend_name == "codex":
            inline_env["CODEX_HOME"] = str(env["CODEX_HOME"])
        else:
            inline_env["PI_HOME"] = str(env["PI_HOME"])
        if resume_session_id is not None:
            inline_env["CODEX_WEB_RESUME_SESSION_ID"] = resume_session_id
        if model_provider is not None:
            inline_env["CODEX_WEB_MODEL_PROVIDER"] = model_provider
        if preferred_auth_method is not None:
            inline_env["CODEX_WEB_PREFERRED_AUTH_METHOD"] = preferred_auth_method
        if model is not None:
            inline_env["CODEX_WEB_MODEL"] = model
        if reasoning_effort is not None:
            inline_env["CODEX_WEB_REASONING_EFFORT"] = reasoning_effort
        if service_tier is not None:
            inline_env["CODEX_WEB_SERVICE_TIER"] = service_tier
        codex_bin = sv.api.clean_optional_text(sv.api.os.environ.get("CODEX_BIN"))
        if codex_bin is not None:
            inline_env["CODEX_BIN"] = codex_bin
        repo_root = Path(sv.api.__file__).resolve().parent.parent
        inline_argv = ["env", *[f"{key}={value}" for key, value in inline_env.items()], *argv]
        shell_cmd = f"cd {sv.api.shlex.quote(str(repo_root))} && exec {sv.api.shlex.join(inline_argv)}"
        has_session = sv.api.subprocess.run(
            [tmux_bin, "has-session", "-t", sv.api.TMUX_SESSION_NAME],
            stdout=sv.api.subprocess.DEVNULL,
            stderr=sv.api.subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if has_session.returncode == 0:
            tmux_argv = [
                tmux_bin,
                "new-window",
                "-d",
                "-P",
                "-F",
                "#{pane_id}",
                "-t",
                f"{sv.api.TMUX_SESSION_NAME}:",
                "-n",
                tmux_window,
                shell_cmd,
            ]
        else:
            tmux_argv = [
                tmux_bin,
                "new-session",
                "-d",
                "-P",
                "-F",
                "#{pane_id}",
                "-s",
                sv.api.TMUX_SESSION_NAME,
                "-n",
                tmux_window,
                shell_cmd,
            ]
        tmux_proc = sv.api.subprocess.run(tmux_argv, capture_output=True, text=True, env=env, check=False)
        if tmux_proc.returncode != 0:
            detail = (tmux_proc.stderr or tmux_proc.stdout or f"exit status {tmux_proc.returncode}").strip()
            raise RuntimeError(f"tmux launch failed: {detail}")
        meta = sv.api.spawn_utils.service(sv).wait_for_spawned_broker_meta(spawn_nonce)
        payload = sv.api.spawn_utils.service(sv).spawn_result_from_meta(meta)
        return {**payload, "tmux_session": sv.api.TMUX_SESSION_NAME, "tmux_window": tmux_window}

    try:
        proc = sv.api.subprocess.Popen(
            argv,
            stdin=sv.api.subprocess.DEVNULL,
            stdout=sv.api.subprocess.DEVNULL,
            stderr=sv.api.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
    except Exception as exc:
        raise RuntimeError(f"spawn failed: {exc}") from exc

    sv.api.spawn_utils.service(sv).wait_or_raise(proc, label="broker", timeout_s=1.5)
    if proc.stderr is not None:
        sv.api.threading.Thread(target=sv.api.drain_stream, args=(proc.stderr,), daemon=True).start()

    sv.api.threading.Thread(target=proc.wait, daemon=True).start()
    meta = sv.api.spawn_utils.service(sv).wait_for_spawned_broker_meta(spawn_nonce)
    payload = sv.api.spawn_utils.service(sv).spawn_result_from_meta(meta)
    sv.api.event_publish.service(sv).publish_sessions_invalidate(reason="session_created")
    return payload

