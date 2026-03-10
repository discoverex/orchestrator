from __future__ import annotations

import importlib.metadata
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from colab_exec import log_step, run_command
from colab_runtime import ColabRuntimeConfig, load_dotenv, prefect_env, require_env


@dataclass(frozen=True)
class WorkerStatusResult:
    running: bool
    pid: int | None
    message: str


@dataclass(frozen=True)
class WorkerStartResult:
    pid: int
    log_file: Path
    checkpoint_dir: Path


def ensure_drive_checkpoint_dir(path: Path) -> None:
    resolved = path.resolve()
    if str(resolved).startswith("/content/drive") and not Path(
        "/content/drive/MyDrive"
    ).exists():
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
            "worker", "warning: --skip-install is deprecated; bootstrap handles installation"
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
        f"{Path('/content/venv') / 'bin' / 'python'} "
        "infra/stacks/worker/colab/colab_worker_runner.py start"
    )


def read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def worker_status(pid_file: Path) -> WorkerStatusResult:
    pid = read_pid(pid_file)
    if not pid:
        return WorkerStatusResult(False, None, "worker status: stopped (no pid file)")
    if not is_running(pid):
        return WorkerStatusResult(False, pid, f"worker status: stopped (stale pid={pid})")
    return WorkerStatusResult(True, pid, f"worker status: running (pid={pid})")


def read_worker_logs(log_file: Path, tail: int) -> list[str]:
    if not log_file.exists():
        raise RuntimeError(f"log file not found: {log_file}")
    lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-tail:]


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
    log_step("worker", f"worker started pid={proc.pid}")
    log_step("worker", f"log file: {config.log_file}")
    log_step("worker", f"checkpoint dir: {config.checkpoint_dir}")
    return WorkerStartResult(proc.pid, config.log_file, config.checkpoint_dir)


def stop_worker(pid_file: Path) -> WorkerStatusResult:
    pid = read_pid(pid_file)
    if not pid:
        return WorkerStatusResult(False, None, "worker already stopped")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        pid_file.unlink()
    except OSError:
        pass
    return WorkerStatusResult(False, pid, f"worker stopped pid={pid}")
