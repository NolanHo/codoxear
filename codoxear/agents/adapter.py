from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class AgentAdapter(Protocol):
    backend: str

    def sock_call(
        self,
        sock_path: Path,
        req: dict[str, Any],
        *,
        timeout_s: float,
    ) -> dict[str, Any]: ...

    def shutdown(self, sock_path: Path, *, timeout_s: float = 1.0) -> dict[str, Any]: ...

    def read_state(self, sock_path: Path, *, timeout_s: float = 1.5) -> dict[str, Any]: ...

    def read_tail(self, sock_path: Path, *, timeout_s: float = 1.5) -> dict[str, Any]: ...

    def inject_keys(
        self,
        sock_path: Path,
        seq: str,
        *,
        timeout_s: float = 2.0,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class SocketAgentAdapter:
    backend: str

    def sock_call(
        self,
        sock_path: Path,
        req: dict[str, Any],
        *,
        timeout_s: float,
    ) -> dict[str, Any]:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout_s)
        try:
            s.connect(str(sock_path))
            s.sendall((json.dumps(req) + "\n").encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
            line = buf.split(b"\n", 1)[0]
            if not line:
                return {"error": "empty response"}
            payload = json.loads(line.decode("utf-8"))
            return payload if isinstance(payload, dict) else {"error": "invalid response"}
        finally:
            s.close()

    def shutdown(self, sock_path: Path, *, timeout_s: float = 1.0) -> dict[str, Any]:
        return self.sock_call(sock_path, {"cmd": "shutdown"}, timeout_s=timeout_s)

    def read_state(self, sock_path: Path, *, timeout_s: float = 1.5) -> dict[str, Any]:
        return self.sock_call(sock_path, {"cmd": "state"}, timeout_s=timeout_s)

    def read_tail(self, sock_path: Path, *, timeout_s: float = 1.5) -> dict[str, Any]:
        return self.sock_call(sock_path, {"cmd": "tail"}, timeout_s=timeout_s)

    def inject_keys(
        self,
        sock_path: Path,
        seq: str,
        *,
        timeout_s: float = 2.0,
    ) -> dict[str, Any]:
        return self.sock_call(sock_path, {"cmd": "keys", "seq": seq}, timeout_s=timeout_s)


_PI_ADAPTER = SocketAgentAdapter("pi")
_CODEX_ADAPTER = SocketAgentAdapter("codex")


def get_agent_adapter(backend: str | None) -> AgentAdapter:
    if str(backend or "").strip().lower() == "pi":
        return _PI_ADAPTER
    return _CODEX_ADAPTER
