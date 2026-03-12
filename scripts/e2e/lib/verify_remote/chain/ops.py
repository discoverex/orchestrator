from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from .errors import VerifyError


def run_ops_script(
    script_rel_path: str, env_overrides: dict[str, str], argv: list[str]
) -> dict[str, Any]:
    script_path = (
        Path(__file__).resolve().parents[5] / "scripts" / "ops" / script_rel_path
    )
    if shutil.which("uv"):
        cmd = ["uv", "run", "python", str(script_path), *argv]
    else:
        cmd = [sys.executable, str(script_path), *argv]
    env = os.environ.copy()
    env.update(env_overrides)
    proc = subprocess.run(cmd, check=False, text=True, capture_output=True, env=env)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        raise VerifyError(
            "ops-script", "SCRIPT_FAILED", f"{script_rel_path} failed: {detail}"
        )
    stdout = proc.stdout.strip()
    if not stdout:
        return {}
    parsed = json.loads(stdout)
    if not isinstance(parsed, dict):
        raise VerifyError(
            "ops-script",
            "SCRIPT_BAD_JSON",
            f"{script_rel_path} returned non-object JSON",
        )
    return cast(dict[str, Any], parsed)
