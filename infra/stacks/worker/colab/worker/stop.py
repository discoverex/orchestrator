from __future__ import annotations

import os
import signal
from pathlib import Path

from .logs import append_worker_log_banner
from .models import WorkerStatusResult
from .status import read_pid, wait_for_exit


def stop_worker(
    pid_file: Path,
    log_file: Path | None = None,
) -> WorkerStatusResult:
    pid = read_pid(pid_file)
    if not pid:
        return WorkerStatusResult(False, None, "worker already stopped")
    stopped = False
    try:
        os.killpg(pid, signal.SIGTERM)
        stopped = wait_for_exit(pid)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
            stopped = wait_for_exit(pid)
        except OSError:
            stopped = True
    if not stopped:
        try:
            os.killpg(pid, signal.SIGKILL)
            stopped = wait_for_exit(pid, timeout_seconds=2.0)
        except OSError:
            try:
                os.kill(pid, signal.SIGKILL)
                stopped = wait_for_exit(pid, timeout_seconds=2.0)
            except OSError:
                stopped = True
    if not stopped:
        if log_file is not None:
            append_worker_log_banner(
                log_file,
                position="bottom",
                pid=pid,
                note="stop timed out; process still running",
            )
        return WorkerStatusResult(
            True,
            pid,
            f"worker stop timed out pid={pid}; process still running",
        )
    try:
        pid_file.unlink()
    except OSError:
        pass
    if log_file is not None:
        append_worker_log_banner(log_file, position="bottom", pid=pid)
    return WorkerStatusResult(False, pid, f"worker stopped pid={pid}")
