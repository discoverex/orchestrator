from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from runner.adapters.outbound.git.errors import RunnerError

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
logger = logging.getLogger("runner.git.repo")


def run_command(cmd: list[str], cwd: Path | None = None) -> str:
    logger.info("running git command", extra={"cmd": cmd, "cwd": str(cwd or "")})
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error(
            "git command failed",
            extra={
                "cmd": cmd,
                "cwd": str(cwd or ""),
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            },
        )
        raise RunnerError(f"command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def safe_directory_args(repo_path: Path) -> list[str]:
    resolved = repo_path.resolve()
    return [
        "-c",
        f"safe.directory={resolved}",
        "-c",
        f"safe.directory={resolved / '.git'}",
    ]


def checkout_target(ref: str | None, resolved_commit: str) -> str:
    candidate = (ref or "").strip()
    if candidate and not _SHA1.match(candidate.lower()):
        return candidate
    return resolved_commit
