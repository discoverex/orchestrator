from __future__ import annotations

import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    cmd: tuple[str, ...]
    returncode: int
    output: str
    duration_seconds: float


def log_step(step: str, message: str) -> None:
    print(f"[{step}] {message}", flush=True)


def format_command(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def run_command(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    step: str,
) -> CommandResult:
    started = time.monotonic()
    log_step(step, f"START {format_command(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.append(line)
        sys.stdout.write(line)
        sys.stdout.flush()

    returncode = proc.wait()
    duration = time.monotonic() - started
    output = "".join(lines)
    if returncode != 0 and check:
        log_step(step, f"FAILED rc={returncode} after {duration:.1f}s")
        raise RuntimeError(f"{step} failed with rc={returncode}: {format_command(cmd)}")

    status = "DONE" if returncode == 0 else "FAILED"
    log_step(step, f"{status} rc={returncode} after {duration:.1f}s")
    return CommandResult(
        cmd=tuple(cmd),
        returncode=returncode,
        output=output,
        duration_seconds=duration,
    )
