from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    output: str
    returncode: int


def log_step(step: str, message: str) -> None:
    print(f"[{step}] {message}")


def run_command(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
    check: bool = True,
    step: str = "run",
) -> CommandResult:

    log_step(step, f"exec: {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\n"
            f"stdout: {proc.stdout.strip()}\n"
            f"stderr: {proc.stderr.strip()}"
        )
    return CommandResult(output=proc.stdout, returncode=proc.returncode)
