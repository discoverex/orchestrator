from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import mkdtemp

from .models import RunArtifacts

_SHA1 = re.compile(r"^[0-9a-f]{40}$")


class RunnerError(RuntimeError):
    pass


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RunnerError(f"command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def resolve_commit(repo_url: str, ref: str) -> str:
    candidate = ref.strip().lower()
    if _SHA1.match(candidate):
        return candidate

    for remote_ref in (f"refs/heads/{ref}", f"refs/tags/{ref}", ref):
        try:
            out = _run(["git", "ls-remote", repo_url, remote_ref])
        except RunnerError:
            continue
        if not out:
            continue
        line = out.splitlines()[0]
        commit = line.split()[0]
        if _SHA1.match(commit):
            return commit
    raise RunnerError(f"unable to resolve ref={ref} for repo={repo_url}")


def run_entrypoint(
    repo_url: str,
    resolved_commit: str,
    entrypoint: list[str],
    env: dict[str, str] | None = None,
) -> RunArtifacts:
    workdir = Path(mkdtemp(prefix="orchestrator-run-"))

    _run(["git", "clone", "--filter=blob:none", repo_url, str(workdir)])
    _run(["git", "checkout", resolved_commit], cwd=workdir)

    stdout_path = workdir / "stdout.log"
    stderr_path = workdir / "stderr.log"
    result_path = workdir / "result.json"

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    with stdout_path.open("w", encoding="utf-8") as stdout_f, stderr_path.open("w", encoding="utf-8") as stderr_f:
        proc = subprocess.run(entrypoint, cwd=workdir, env=merged_env, stdout=stdout_f, stderr=stderr_f, text=True)

    result_path.write_text(
        json.dumps(
            {
                "exit_code": proc.returncode,
                "resolved_commit": resolved_commit,
                "entrypoint": entrypoint,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    return RunArtifacts(
        workdir=workdir,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        result_path=result_path,
        exit_code=proc.returncode,
    )


def cleanup_workdir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
