from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from runner.adapters.outbound.git.errors import RunnerError

_GITHUB_SSH = re.compile(r"^git@github\.com:(?P<repo>.+?)(?:\.git)?$")


def worker_cache_root() -> Path:
    cache_dir = os.getenv("ORCH_CACHE_DIR", "").strip()
    if cache_dir:
        return Path(cache_dir)

    runtime_dir = os.getenv("ORCH_WORKER_RUNTIME_DIR", "").strip()
    if runtime_dir:
        return Path(runtime_dir) / "cache"

    return Path("/var/lib/orchestrator/cache")


def repo_cache_root() -> Path:
    override = os.getenv("ORCH_REPO_CACHE_DIR", "").strip()
    if override:
        return Path(override)
    return worker_cache_root() / "repo"


def repo_runtime_root() -> Path:
    override = os.getenv("ORCH_REPO_RUNTIME_DIR", "").strip()
    if override:
        return Path(override)
    runtime_dir = os.getenv("ORCH_WORKER_RUNTIME_DIR", "").strip()
    if runtime_dir:
        return Path(runtime_dir) / "repos"
    return Path("/var/lib/orchestrator/repos")


def normalized_repo_url(repo_url: str) -> str:
    match = _GITHUB_SSH.match(repo_url.strip())
    if not match:
        return repo_url
    return f"https://github.com/{match.group('repo')}.git"


def repo_runtime_name(repo_url: str) -> str:
    normalized = normalized_repo_url(repo_url).rstrip("/")
    split = urlsplit(normalized)
    if split.scheme:
        path_parts = [
            part for part in Path(unquote(split.path)).parts if part not in ("/", "")
        ]
    else:
        path_parts = [part for part in Path(normalized).parts if part not in (".", "")]
    if not path_parts:
        raise RunnerError(f"unable to derive repo name from repo_url={repo_url}")
    repo_name = path_parts[-1].removesuffix(".git").strip()
    owner_name = path_parts[-2].strip() if len(path_parts) >= 2 else ""
    base_name = f"{owner_name}__{repo_name}" if owner_name else repo_name
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", base_name)
    return sanitized or "repo"


def repo_runtime_path(repo_url: str) -> Path:
    return repo_runtime_root() / repo_runtime_name(repo_url)


def local_repo_path(repo_url: str) -> Path | None:
    split = urlsplit(repo_url)
    if split.scheme == "file":
        return Path(unquote(split.path))
    if split.scheme:
        return None
    candidate = Path(repo_url)
    return candidate if candidate.exists() else None
