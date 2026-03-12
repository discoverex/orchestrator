from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkerStatusResult:
    running: bool
    pid: int | None
    message: str


@dataclass(frozen=True)
class WorkerStartResult:
    pid: int
    log_file: Path
    checkpoint_dir: Path
