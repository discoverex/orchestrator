from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def _worker_log_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S %Z")


def append_worker_log_banner(
    log_file: Path,
    *,
    position: str,
    pid: int | None,
    work_pool: str | None = None,
    work_queue: str | None = None,
    note: str | None = None,
) -> None:
    line = "=" * 72 if position == "top" else "-" * 72
    details = [f"time={_worker_log_timestamp()}"]
    if pid is not None:
        details.append(f"pid={pid}")
    if work_pool:
        details.append(f"pool={work_pool}")
    if work_queue:
        details.append(f"queue={work_queue}")
    if note:
        details.append(note)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as logf:
        logf.write(f"{line}\n")
        logf.write(f"worker {'start' if position == 'top' else 'stop'} | ")
        logf.write(" | ".join(details))
        logf.write("\n")
        logf.write(f"{line}\n")


def read_worker_logs(log_file: Path, tail: int) -> list[str]:
    if not log_file.exists():
        raise RuntimeError(f"log file not found: {log_file}")
    lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-tail:]
