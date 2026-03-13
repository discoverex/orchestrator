from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from .bootstrap import BootstrapResult, bootstrap_runtime
from .exec import log_step, run_command
from .logs import read_worker_logs
from .models import WorkerStartResult, WorkerStatusResult
from .repo import RepoSyncResult, sync_repo
from .runtime import (
    DEFAULT_CACHE_ROOT,
    DEFAULT_CHECKPOINT_DIR,
    DEFAULT_LOG_PATH,
    DEFAULT_PID_PATH,
    DEFAULT_REPO_DIR,
    ColabRuntimeConfig,
    populate_colab_env,
)
from .start import start_worker
from .status import worker_status
from .stop import stop_worker


def build_runtime_config(
    *,
    repo_dir: Path = DEFAULT_REPO_DIR,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR,
    pid_file: Path = DEFAULT_PID_PATH,
    log_file: Path = DEFAULT_LOG_PATH,
    python_bin: str = "python3",
) -> ColabRuntimeConfig:
    return ColabRuntimeConfig(
        repo_dir=repo_dir,
        cache_root=cache_root,
        checkpoint_dir=checkpoint_dir,
        pid_file=pid_file,
        log_file=log_file,
        python_bin=python_bin,
    )


def configure_notebook_env(
    config: ColabRuntimeConfig,
    *,
    secret_reader: Callable[[str], str | None] | None = None,
) -> dict[str, object]:
    snapshot = populate_colab_env(config, secret_reader=secret_reader)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return snapshot


def clone_repo_if_missing(config: ColabRuntimeConfig, repo_url: str) -> None:
    config.repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if config.repo_dir.exists():
        log_step("repo", f"repo already exists at {config.repo_dir}")
        return
    run_command(
        ["git", "clone", repo_url, str(config.repo_dir)],
        cwd=config.repo_dir.parent,
        step="repo",
    )


def sync_notebook_repo(
    config: ColabRuntimeConfig, *, repo_url: str, branch: str
) -> RepoSyncResult:
    return sync_repo(config, repo_url=repo_url, branch=branch)


def bootstrap_notebook_runtime(config: ColabRuntimeConfig) -> BootstrapResult:
    result = bootstrap_runtime(config)
    print(result.python_version)
    print(result.package_metadata)
    return result


def restart_worker(config: ColabRuntimeConfig, *, tail: int = 120) -> WorkerStartResult:
    stop_message = stop_worker(config.pid_file, config.log_file)
    print(stop_message.message)
    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    config.log_file.write_text("", encoding="utf-8")
    result = start_worker(config, skip_install=True, cwd=config.repo_dir)
    status = worker_status(config.pid_file)
    print(status.message)
    for line in read_worker_logs(config.log_file, tail):
        print(line)
    return result


def show_worker_status(config: ColabRuntimeConfig) -> WorkerStatusResult:
    status = worker_status(config.pid_file)
    print(status.message)
    return status


def show_worker_logs(config: ColabRuntimeConfig, *, tail: int = 120) -> list[str]:
    lines = read_worker_logs(config.log_file, tail)
    for line in lines:
        print(line)
    return lines


def stop_notebook_worker(config: ColabRuntimeConfig) -> WorkerStatusResult:
    status = stop_worker(config.pid_file, config.log_file)
    print(status.message)
    return status
