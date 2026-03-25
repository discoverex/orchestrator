from __future__ import annotations

from dataclasses import dataclass

from .exec import log_step, run_command
from .runtime import ColabRuntimeConfig


@dataclass(frozen=True)
class RepoSyncResult:
    repo_url: str
    branch: str
    cloned: bool


def sync_repo(
    config: ColabRuntimeConfig, *, repo_url: str, branch: str
) -> RepoSyncResult:
    config.cache_root.parent.mkdir(parents=True, exist_ok=True)
    cloned = False
    if not config.repo_dir.exists():
        run_command(
            ["git", "clone", repo_url, str(config.repo_dir)],
            cwd=config.repo_dir.parent,
            step="repo",
        )
        cloned = True
    else:
        log_step("repo", f"using existing repo at {config.repo_dir}")

    run_command(["git", "fetch", "--all", "--prune"], cwd=config.repo_dir, step="repo")
    run_command(["git", "checkout", branch], cwd=config.repo_dir, step="repo")
    run_command(["git", "fetch", "origin"], cwd=config.repo_dir, step="repo")
    run_command(
        ["git", "reset", "--hard", f"origin/{branch}"],
        cwd=config.repo_dir,
        step="repo",
    )
    return RepoSyncResult(repo_url=repo_url, branch=branch, cloned=cloned)
