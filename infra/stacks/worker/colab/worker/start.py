from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

from .exec import log_step, run_command
from .logs import append_worker_log_banner
from .models import WorkerStartResult
from .runtime import ColabRuntimeConfig, load_dotenv, prefect_env, require_env
from .status import is_running, read_pid


def ensure_drive_checkpoint_dir(path: Path) -> None:
    resolved = path.resolve()
    if (
        str(resolved).startswith("/content/drive")
        and not Path("/content/drive/MyDrive").exists()
    ):
        raise RuntimeError(
            "Google Drive is not mounted; run drive.mount('/content/drive') first"
        )
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise RuntimeError(f"checkpoint path is not a directory: {path}")
    os.environ["ORCHESTRATOR_CHECKPOINT_DIR"] = str(path)


def ensure_runtime_ready(skip_install: bool) -> None:
    if skip_install:
        log_step(
            "worker",
            "warning: --skip-install is deprecated; bootstrap handles installation",
        )
    try:
        version = importlib.metadata.version("prefect")
    except importlib.metadata.PackageNotFoundError:
        version = None
    if version:
        major = version.split(".", 1)[0]
        if major.isdigit() and int(major) >= 3:
            return
    raise RuntimeError(
        "prefect>=3 is not installed in the current interpreter. "
        "Run bootstrap first, then start the worker with "
        f"{sys.executable} "
        "infra/stacks/worker/colab/runner.py start"
    )


def _probe_prefect_api(env: dict[str, str]) -> None:
    headers_json = env.get("PREFECT_CLIENT_CUSTOM_HEADERS", "")
    if not headers_json:
        raise RuntimeError("PREFECT_CLIENT_CUSTOM_HEADERS is empty")
    headers = json.loads(headers_json)
    api_url = env["PREFECT_API_URL"].rstrip("/")
    work_pool = env["PREFECT_WORK_POOL"]
    probe = run_command(
        [
            "curl",
            "-fsS",
            "-H",
            f"CF-Access-Client-Id: {headers['CF-Access-Client-Id']}",
            "-H",
            f"CF-Access-Client-Secret: {headers['CF-Access-Client-Secret']}",
            f"{api_url}/work_pools/{work_pool}",
        ],
        env=env,
        check=False,
        step="worker",
    )
    if probe.returncode != 0:
        raise RuntimeError("prefect API probe failed before worker start")


def start_worker(
    config: ColabRuntimeConfig,
    *,
    skip_install: bool,
    cwd: Path,
) -> WorkerStartResult:
    load_dotenv()
    require_env()
    ensure_drive_checkpoint_dir(config.checkpoint_dir)
    ensure_runtime_ready(skip_install)
    env = prefect_env()

    log_step("worker", f"prefect api url: {env.get('PREFECT_API_URL', '')}")
    log_step("worker", f"prefect work pool: {env.get('PREFECT_WORK_POOL', '')}")
    log_step("worker", f"prefect work queue: {env.get('PREFECT_WORK_QUEUE', '')}")
    log_step(
        "worker",
        f"prefect custom headers: {env.get('PREFECT_CLIENT_CUSTOM_HEADERS', '')}",
    )

    _probe_prefect_api(env)
    run_command(
        [
            sys.executable,
            "-m",
            "prefect",
            "config",
            "set",
            f"PREFECT_API_URL={env['PREFECT_API_URL']}",
        ],
        env=env,
        step="worker",
    )
    run_command(
        [
            sys.executable,
            "-m",
            "prefect",
            "work-pool",
            "create",
            env["PREFECT_WORK_POOL"],
            "--type",
            "process",
        ],
        env=env,
        check=False,
        step="worker",
    )

    existing = read_pid(config.pid_file)
    if existing and is_running(existing):
        log_step("worker", f"worker already running (pid={existing})")
        return WorkerStartResult(existing, config.log_file, config.checkpoint_dir)

    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    with config.log_file.open("a", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "prefect",
                "worker",
                "start",
                "--pool",
                env["PREFECT_WORK_POOL"],
                "--work-queue",
                env["PREFECT_WORK_QUEUE"],
                "--type",
                "process",
            ],
            stdout=logf,
            stderr=subprocess.STDOUT,
            env=env,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=cwd,
        )
    config.pid_file.write_text(str(proc.pid), encoding="utf-8")
    append_worker_log_banner(
        config.log_file,
        position="top",
        pid=proc.pid,
        work_pool=env["PREFECT_WORK_POOL"],
        work_queue=env["PREFECT_WORK_QUEUE"],
    )
    log_step("worker", f"worker started pid={proc.pid}")
    log_step("worker", f"log file: {config.log_file}")
    log_step("worker", f"checkpoint dir: {config.checkpoint_dir}")
    return WorkerStartResult(proc.pid, config.log_file, config.checkpoint_dir)
