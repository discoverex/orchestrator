from __future__ import annotations

import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

from runner.adapters.outbound.git.common import (
    _SHA1,
    checkout_target,
    logger,
    run_command,
    safe_directory_args,
)
from runner.adapters.outbound.git.paths import (
    local_repo_path,
    normalized_repo_url,
    repo_cache_root,
    repo_runtime_path,
    repo_runtime_root,
)


def prepare_cached_repo(repo_url: str, ref: str | None, resolved_commit: str) -> Path:
    normalized = normalized_repo_url(repo_url)
    cache_root = repo_cache_root()
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_repo = cache_root / sha256(normalized.encode("utf-8")).hexdigest()[:16]
    local_repo = local_repo_path(normalized)
    clone_source = (
        local_repo.resolve().as_uri() if local_repo is not None else normalized
    )
    logger.info(
        "preparing cached repo",
        extra={
            "repo_url": repo_url,
            "normalized_repo_url": normalized,
            "ref": ref or "",
            "resolved_commit": resolved_commit,
            "cache_root": str(cache_root),
            "cache_repo": str(cache_repo),
            "clone_source": clone_source,
            "cache_exists": cache_repo.exists(),
        },
    )
    if (cache_repo / ".git").exists():
        logger.info("reusing cached repo", extra={"cache_repo": str(cache_repo)})
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
    logger.info(
        "checking out cached repo target",
        extra={"cache_repo": str(cache_repo), "target": target},
    )
    run_command(["git", "checkout", target], cwd=cache_repo)
    run_command(["git", "reset", "--hard"], cwd=cache_repo)
    run_command(["git", "clean", "-fdx"], cwd=cache_repo)
    logger.info("cached repo ready", extra={"cache_repo": str(cache_repo)})
    return cache_repo


def prepare_runtime_repo(repo_url: str, ref: str | None, resolved_commit: str) -> Path:
    normalized = normalized_repo_url(repo_url)
    runtime_root = repo_runtime_root()
    runtime_root.mkdir(parents=True, exist_ok=True)
    runtime_repo = repo_runtime_path(normalized)
    local_repo = local_repo_path(normalized)
    clone_source = (
        local_repo.resolve().as_uri() if local_repo is not None else normalized
    )
    logger.info(
        "preparing runtime repo",
        extra={
            "repo_url": repo_url,
            "normalized_repo_url": normalized,
            "ref": ref or "",
            "resolved_commit": resolved_commit,
            "runtime_root": str(runtime_root),
            "runtime_repo": str(runtime_repo),
            "clone_source": clone_source,
            "runtime_exists": runtime_repo.exists(),
        },
    )
    if (runtime_repo / ".git").exists():
        run_command(
            ["git", "remote", "set-url", "origin", clone_source], cwd=runtime_repo
        )
        run_command(["git", "fetch", "origin", "--tags", "--prune"], cwd=runtime_repo)
    else:
        if runtime_repo.exists():
            shutil.rmtree(runtime_repo, ignore_errors=True)
        clone_cmd = ["git"]
        if local_repo is not None:
            clone_cmd.extend(safe_directory_args(local_repo))
        clone_cmd.extend(
            [
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                clone_source,
                str(runtime_repo),
            ]
        )
        run_command(clone_cmd)

    target = checkout_target(ref, resolved_commit)
    logger.info(
        "checking out runtime repo target",
        extra={"runtime_repo": str(runtime_repo), "target": target},
    )
    if ref and ref.strip() and not _SHA1.match(ref.strip().lower()):
        remote_branch = f"refs/remotes/origin/{ref}"
        branch_exists = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", remote_branch],
            cwd=runtime_repo,
            capture_output=True,
            text=True,
        )
        if branch_exists.returncode == 0:
            run_command(["git", "checkout", "-B", ref, remote_branch], cwd=runtime_repo)
        else:
            run_command(["git", "checkout", "--force", target], cwd=runtime_repo)
    else:
        run_command(["git", "checkout", "--force", target], cwd=runtime_repo)
    run_command(["git", "reset", "--hard", resolved_commit], cwd=runtime_repo)
    run_command(["git", "clean", "-fdx"], cwd=runtime_repo)
    logger.info("runtime repo ready", extra={"runtime_repo": str(runtime_repo)})
    return runtime_repo
