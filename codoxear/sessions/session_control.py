from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import control_queue as _control_queue
from . import restart_handoff as _restart_handoff
from . import spawn_flow as _spawn_flow


@dataclass(slots=True)
class SessionControlService:
    manager: Any

    def send(self, session_id: str, text: str) -> dict[str, Any]:
        return send(self.manager, session_id, text)

    def enqueue(self, session_id: str, text: str) -> dict[str, Any]:
        return enqueue(self.manager, session_id, text)

    def queue_list(self, session_id: str) -> list[str]:
        return queue_list(self.manager, session_id)

    def queue_delete(self, session_id: str, index: int) -> dict[str, Any]:
        return queue_delete(self.manager, session_id, int(index))

    def queue_update(self, session_id: str, index: int, text: str) -> dict[str, Any]:
        return queue_update(self.manager, session_id, int(index), text)

    def spawn_web_session(
        self,
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
        return spawn_web_session(
            self.manager,
            cwd=cwd,
            args=args,
            agent_backend=agent_backend,
            resume_session_id=resume_session_id,
            worktree_branch=worktree_branch,
            model_provider=model_provider,
            preferred_auth_method=preferred_auth_method,
            model=model,
            reasoning_effort=reasoning_effort,
            service_tier=service_tier,
            create_in_tmux=create_in_tmux,
            backend=backend,
        )

    def restart_session(self, session_id: str) -> dict[str, Any]:
        return restart_session(self.manager, session_id)

    def handoff_session(self, session_id: str) -> dict[str, Any]:
        return handoff_session(self.manager, session_id)


def service(manager: Any) -> SessionControlService:
    return SessionControlService(manager)


def send(manager: Any, session_id: str, text: str) -> dict[str, Any]:
    return _control_queue.send(manager, session_id, text)


def enqueue(manager: Any, session_id: str, text: str) -> dict[str, Any]:
    return _control_queue.enqueue(manager, session_id, text)


def queue_list(manager: Any, session_id: str) -> list[str]:
    return _control_queue.queue_list(manager, session_id)


def queue_delete(manager: Any, session_id: str, index: int) -> dict[str, Any]:
    return _control_queue.queue_delete(manager, session_id, int(index))


def queue_update(manager: Any, session_id: str, index: int, text: str) -> dict[str, Any]:
    return _control_queue.queue_update(manager, session_id, int(index), text)


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
    return _spawn_flow.spawn_web_session(
        manager,
        cwd=cwd,
        args=args,
        agent_backend=agent_backend,
        resume_session_id=resume_session_id,
        worktree_branch=worktree_branch,
        model_provider=model_provider,
        preferred_auth_method=preferred_auth_method,
        model=model,
        reasoning_effort=reasoning_effort,
        service_tier=service_tier,
        create_in_tmux=create_in_tmux,
        backend=backend,
    )


def restart_session(manager: Any, session_id: str) -> dict[str, Any]:
    return _restart_handoff.restart_session(manager, session_id)


def handoff_session(manager: Any, session_id: str) -> dict[str, Any]:
    return _restart_handoff.handoff_session(manager, session_id)
