from __future__ import annotations

import os
import time
from pathlib import Path

from colab_worker_models import WorkerStatusResult


def read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def worker_status(pid_file: Path) -> WorkerStatusResult:
    pid = read_pid(pid_file)
    if not pid:
        return WorkerStatusResult(False, None, "worker status: stopped (no pid file)")
    if not is_running(pid):
        return WorkerStatusResult(
            False, pid, f"worker status: stopped (stale pid={pid})"
        )
    return WorkerStatusResult(True, pid, f"worker status: running (pid={pid})")


def wait_for_exit(pid: int, timeout_seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_running(pid):
            return True
        time.sleep(0.2)
    return not is_running(pid)
