from __future__ import annotations

from runner.adapters.outbound.git.checkout import (
    prepare_cached_repo,
    prepare_runtime_repo,
)
from runner.adapters.outbound.git.common import (
    _SHA1,
    checkout_target,
    logger,
    run_command,
    safe_directory_args,
)
from runner.adapters.outbound.git.errors import RunnerError
from runner.adapters.outbound.git.paths import (
    local_repo_path,
    normalized_repo_url,
    repo_cache_root,
    repo_runtime_name,
    repo_runtime_path,
    repo_runtime_root,
    worker_cache_root,
)


def resolve_commit(repo_url: str, ref: str) -> str:
    logger.info("resolving commit", extra={"repo_url": repo_url, "ref": ref})
    candidate = ref.strip().lower()
    if _SHA1.match(candidate):
        logger.info("ref already resolved sha", extra={"ref": ref})
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


__all__ = [
    "RunnerError",
    "_SHA1",
    "checkout_target",
    "local_repo_path",
    "normalized_repo_url",
    "prepare_cached_repo",
    "prepare_runtime_repo",
    "repo_cache_root",
    "repo_runtime_name",
    "repo_runtime_path",
    "repo_runtime_root",
    "resolve_commit",
    "run_command",
    "safe_directory_args",
    "worker_cache_root",
]
