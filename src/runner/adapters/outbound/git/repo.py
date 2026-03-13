from __future__ import annotations

import os
import re
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlsplit

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_GITHUB_SSH = re.compile(r"^git@github\.com:(?P<repo>.+?)(?:\.git)?$")


class RunnerError(RuntimeError):
    pass


def run_command(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RunnerError(f"command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def repo_cache_root() -> Path:
    return Path(os.getenv("ORCH_REPO_CACHE_DIR", "/var/lib/orchestrator/repo_cache"))


def normalized_repo_url(repo_url: str) -> str:
    match = _GITHUB_SSH.match(repo_url.strip())
    if not match:
        return repo_url
    return f"https://github.com/{match.group('repo')}.git"


def local_repo_path(repo_url: str) -> Path | None:
    split = urlsplit(repo_url)
    if split.scheme == "file":
        return Path(unquote(split.path))
    if split.scheme:
        return None
    candidate = Path(repo_url)
    return candidate if candidate.exists() else None


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


def resolve_commit(repo_url: str, ref: str) -> str:
    candidate = ref.strip().lower()
    if _SHA1.match(candidate):
        return candidate
    normalized = normalized_repo_url(repo_url)
    local_repo = local_repo_path(normalized)
    if local_repo is not None:
        return run_command(
            [
                "git",
                *safe_directory_args(local_repo),
                "-C",
                str(local_repo),
                "rev-parse",
                ref,
            ]
        )
    for remote_ref in (f"refs/heads/{ref}", f"refs/tags/{ref}", ref):
        try:
            out = run_command(["git", "ls-remote", normalized, remote_ref])
        except RunnerError:
            continue
        if out:
            commit = out.splitlines()[0].split()[0]
            if _SHA1.match(commit):
                return commit
    raise RunnerError(f"unable to resolve ref={ref} for repo={repo_url}")


def prepare_cached_repo(repo_url: str, ref: str | None, resolved_commit: str) -> Path:
    normalized = normalized_repo_url(repo_url)
    cache_root = repo_cache_root()
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_repo = cache_root / sha256(normalized.encode("utf-8")).hexdigest()[:16]
    local_repo = local_repo_path(normalized)
    clone_source = (
        local_repo.resolve().as_uri() if local_repo is not None else normalized
    )
    if (cache_repo / ".git").exists():
        run_command(["git", "fetch", "--all", "--tags", "--prune"], cwd=cache_repo)
    else:
        if cache_repo.exists():
            shutil.rmtree(cache_repo, ignore_errors=True)
        clone_cmd = ["git"]
        if local_repo is not None:
            clone_cmd.extend(safe_directory_args(local_repo))
        clone_cmd.extend(["clone", "--filter=blob:none", clone_source, str(cache_repo)])
        run_command(clone_cmd)
    target = checkout_target(ref, resolved_commit)
    run_command(["git", "checkout", target], cwd=cache_repo)
    run_command(["git", "reset", "--hard"], cwd=cache_repo)
    run_command(["git", "clean", "-fdx"], cwd=cache_repo)
    return cache_repo
