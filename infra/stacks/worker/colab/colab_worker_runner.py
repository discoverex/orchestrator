from __future__ import annotations

import argparse
import importlib.metadata
import os
import signal
import subprocess
import sys
from pathlib import Path

DEFAULT_PID_PATH = Path("/tmp/orchestrator-colab-worker.pid")
DEFAULT_LOG_PATH = Path("/tmp/orchestrator-colab-worker.log")
DEFAULT_CHECKPOINT_DIR = Path("/content/drive/MyDrive/orchestrator/checkpoints")
DEFAULT_REQUIREMENTS_PATH = Path("infra/stacks/worker/colab/requirements-colab.txt")

REQUIRED_ENV = (
    "PREFECT_API_URL",
    "PREFECT_WORK_POOL",
    "STORAGE_GATEWAY_URL",
    "STORAGE_GATEWAY_TOKEN",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Prefect worker in Colab with checkpoint-ready env."
    )
    parser.add_argument("command", choices=("start", "status", "logs", "stop"))
    parser.add_argument("--pid-file", default=str(DEFAULT_PID_PATH))
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--tail", type=int, default=120, help="Used by logs command.")
    parser.add_argument("--checkpoint-dir", default=str(DEFAULT_CHECKPOINT_DIR))
    parser.add_argument("--requirements-file", default=str(DEFAULT_REQUIREMENTS_PATH))
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip pip bootstrap even if Prefect is missing.",
    )
    return parser.parse_args()


def _require_env() -> None:
    missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            f"missing required environment variables: {', '.join(missing)}"
        )


def _ensure_drive_checkpoint_dir(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(
            f"checkpoint directory not found: {path} (mount Google Drive first)"
        )
    if not path.is_dir():
        raise RuntimeError(f"checkpoint path is not a directory: {path}")
    os.environ["ORCHESTRATOR_CHECKPOINT_DIR"] = str(path)


def _prefect_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"src:{pythonpath}" if pythonpath else "src"
    env.setdefault("PREFECT_WORK_QUEUE", "gpu-colab")
    return env


def _run(
    cmd: list[str], env: dict[str, str] | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True, capture_output=True, env=env)


def _prefect_compatible_installed() -> bool:
    try:
        ver = importlib.metadata.version("prefect")
    except importlib.metadata.PackageNotFoundError:
        return False
    major = ver.split(".", 1)[0]
    return major.isdigit() and int(major) >= 3


def _ensure_colab_dependencies(requirements_file: Path, skip_install: bool) -> None:
    if _prefect_compatible_installed():
        return
    if skip_install:
        raise RuntimeError(
            "prefect>=3 is required but not installed (and --skip-install was set)"
        )
    if not requirements_file.exists():
        raise RuntimeError(f"requirements file not found: {requirements_file}")
    _run(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
        check=True,
    )
    if not _prefect_compatible_installed():
        raise RuntimeError("prefect>=3 install failed")


def _read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start(
    pid_file: Path,
    log_file: Path,
    checkpoint_dir: Path,
    requirements_file: Path,
    skip_install: bool,
) -> int:
    _require_env()
    _ensure_drive_checkpoint_dir(checkpoint_dir)
    _ensure_colab_dependencies(requirements_file, skip_install)
    env = _prefect_env()

    _run(
        [
            sys.executable,
            "-m",
            "prefect",
            "config",
            "set",
            f"PREFECT_API_URL={env['PREFECT_API_URL']}",
        ],
        env=env,
    )
    _run(
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
    )

    existing = _read_pid(pid_file)
    if existing and _is_running(existing):
        print(f"worker already running (pid={existing})")
        return 0

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as logf:
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
        )
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    print(f"worker started pid={proc.pid}")
    print(f"log file: {log_file}")
    print(f"checkpoint dir: {checkpoint_dir}")
    return 0


def status(pid_file: Path) -> int:
    pid = _read_pid(pid_file)
    if not pid:
        print("worker status: stopped (no pid file)")
        return 1
    if not _is_running(pid):
        print(f"worker status: stopped (stale pid={pid})")
        return 1
    print(f"worker status: running (pid={pid})")
    return 0


def logs(log_file: Path, tail: int) -> int:
    if not log_file.exists():
        print(f"log file not found: {log_file}")
        return 1
    lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in lines[-tail:]:
        print(line)
    return 0


def stop(pid_file: Path) -> int:
    pid = _read_pid(pid_file)
    if not pid:
        print("worker already stopped")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        pid_file.unlink()
    except OSError:
        pass
    print(f"worker stopped pid={pid}")
    return 0


def main() -> int:
    args = _parse_args()
    pid_file = Path(args.pid_file)
    log_file = Path(args.log_file)
    checkpoint_dir = Path(args.checkpoint_dir)
    requirements_file = Path(args.requirements_file)
    try:
        if args.command == "start":
            return start(
                pid_file, log_file, checkpoint_dir, requirements_file, args.skip_install
            )
        if args.command == "status":
            return status(pid_file)
        if args.command == "logs":
            return logs(log_file, args.tail)
        if args.command == "stop":
            return stop(pid_file)
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
