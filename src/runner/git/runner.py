from __future__ import annotations

import re
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

from runner.entrypoint.core import cleanup_workdir, run_entrypoint
from runner.git.repo import (
    RunnerError,
    local_repo_path,
    normalized_repo_url,
    repo_cache_root,
    safe_directory_args,
)

__all__ = ["RunnerError", "cleanup_workdir", "resolve_commit", "run_entrypoint"]

_SHA1 = re.compile(r"^[0-9a-f]{40}$")


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RunnerError(
            f"command failed: {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout.strip()}\n"
            f"stderr:\n{proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def _local_repo_path(repo_url: str) -> Path | None:
    return local_repo_path(repo_url)


def _repo_cache_path(repo_url: str) -> Path:
    return repo_cache_root() / sha256(repo_url.encode("utf-8")).hexdigest()[:16]


def _safe_directory_args(repo_path: Path) -> list[str]:
    return safe_directory_args(repo_path)


def _checkout_target(ref: str | None, resolved_commit: str) -> str:
    candidate = (ref or "").strip()
    if candidate and not _SHA1.match(candidate.lower()):
        return candidate
    return resolved_commit


def _prepare_cached_repo(repo_url: str, ref: str | None, resolved_commit: str) -> Path:
    normalized = normalized_repo_url(repo_url)
    cache_root = repo_cache_root()
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_repo = _repo_cache_path(normalized)
    local_repo = _local_repo_path(normalized)
    clone_source = (
        local_repo.resolve().as_uri() if local_repo is not None else normalized
    )
    if (cache_repo / ".git").exists():
        _run(["git", "fetch", "--all", "--tags", "--prune"], cwd=cache_repo)
    else:
        if cache_repo.exists():
            shutil.rmtree(cache_repo, ignore_errors=True)
        clone_cmd = ["git"]
        if local_repo is not None:
            clone_cmd.extend(_safe_directory_args(local_repo))
        clone_cmd.extend(["clone", "--filter=blob:none", clone_source, str(cache_repo)])
        _run(clone_cmd)
    target = _checkout_target(ref, resolved_commit)
    _run(["git", "checkout", target], cwd=cache_repo)
    _run(["git", "reset", "--hard"], cwd=cache_repo)
    _run(["git", "clean", "-fdx"], cwd=cache_repo)
    return cache_repo


def _prepare_per_repo_venv(workdir: Path, merged_env: dict[str, str]) -> None:
    uv_bin = shutil.which("uv")
    if not uv_bin:
        return

    venv_dir = workdir / ".venv"
    merged_env["UV_PROJECT_ENVIRONMENT"] = str(venv_dir)
    merged_env["PATH"] = f"{venv_dir / 'bin'}:{merged_env.get('PATH', '')}"
    if not (workdir / "pyproject.toml").exists():
        return

    sync_cmd = (
        [uv_bin, "sync", "--frozen"]
        if (workdir / "uv.lock").exists()
        else [uv_bin, "sync"]
    )
    proc = subprocess.run(
        sync_cmd, cwd=workdir, env=merged_env, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RunnerError(
            f"venv setup failed: {' '.join(sync_cmd)}\n{proc.stderr.strip()}"
        )


def resolve_commit(repo_url: str, ref: str) -> str:
    candidate = ref.strip().lower()
    if _SHA1.match(candidate):
        return candidate
    normalized = normalized_repo_url(repo_url)
    local_repo = _local_repo_path(normalized)
    if local_repo is not None:
        return _run(
            [
                "git",
                *_safe_directory_args(local_repo),
                "-C",
                str(local_repo),
                "rev-parse",
                ref,
            ]
        )
    for remote_ref in (f"refs/heads/{ref}", f"refs/tags/{ref}", ref):
        try:
            out = _run(["git", "ls-remote", normalized, remote_ref])
        except RunnerError:
            continue
        if out:
            commit = out.splitlines()[0].split()[0]
            if _SHA1.match(commit):
                return commit
    raise RunnerError(f"unable to resolve ref={ref} for repo={repo_url}")
