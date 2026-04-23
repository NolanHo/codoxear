from __future__ import annotations

import os
import signal
import time
from typing import Any


def terminate_process_group(
    runtime: Any,
    root_pid: int,
    *,
    wait_seconds: float = 1.0,
) -> bool:
    pids = runtime._descendant_pids(root_pid)
    pids.add(root_pid)
    for pid in sorted(pids, reverse=True):
        if pid <= 0:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError:
            return False
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if all(not runtime._pid_alive(pid) for pid in pids):
            return True
        time.sleep(0.05)
    return all(not runtime._pid_alive(pid) for pid in pids)


def terminate_process(runtime: Any, pid: int, *, wait_seconds: float = 1.0) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if not runtime._pid_alive(pid):
            return True
        time.sleep(0.05)
    return not runtime._pid_alive(pid)
