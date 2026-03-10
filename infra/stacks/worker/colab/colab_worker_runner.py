from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

bootstrap_runtime = importlib.import_module("colab_bootstrap").bootstrap_runtime
runtime = importlib.import_module("colab_runtime")
worker = importlib.import_module("colab_worker")

ColabRuntimeConfig = runtime.ColabRuntimeConfig
DEFAULT_BOOTSTRAP_PYTHON = runtime.DEFAULT_BOOTSTRAP_PYTHON
DEFAULT_CACHE_ROOT = runtime.DEFAULT_CACHE_ROOT
DEFAULT_CHECKPOINT_DIR = runtime.DEFAULT_CHECKPOINT_DIR
DEFAULT_LOG_PATH = runtime.DEFAULT_LOG_PATH
DEFAULT_PID_PATH = runtime.DEFAULT_PID_PATH
DEFAULT_REPO_DIR = runtime.DEFAULT_REPO_DIR
DEFAULT_VENV_DIR = runtime.DEFAULT_VENV_DIR
resolve_path = runtime.resolve_path
read_worker_logs = worker.read_worker_logs
start_worker = worker.start_worker
stop_worker = worker.stop_worker
worker_status = worker.worker_status


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap and run the Colab Prefect worker."
    )
    parser.add_argument(
        "command", choices=("bootstrap", "start", "status", "logs", "stop")
    )
    parser.add_argument("--pid-file", default=str(DEFAULT_PID_PATH))
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--tail", type=int, default=120, help="Used by logs command.")
    parser.add_argument("--checkpoint-dir", default=str(DEFAULT_CHECKPOINT_DIR))
    parser.add_argument("--repo-dir", default=str(DEFAULT_REPO_DIR))
    parser.add_argument("--cache-root", default=str(DEFAULT_CACHE_ROOT))
    parser.add_argument("--venv-dir", default=str(DEFAULT_VENV_DIR))
    parser.add_argument("--python-bin", default=DEFAULT_BOOTSTRAP_PYTHON)
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Deprecated compatibility flag; install must be completed via bootstrap.",
    )
    return parser.parse_args()


def _config_from_args(args: argparse.Namespace) -> ColabRuntimeConfig:
    return ColabRuntimeConfig(
        repo_dir=resolve_path(Path(args.repo_dir)),
        cache_root=resolve_path(Path(args.cache_root)),
        venv_dir=resolve_path(Path(args.venv_dir)),
        checkpoint_dir=resolve_path(Path(args.checkpoint_dir)),
        pid_file=resolve_path(Path(args.pid_file)),
        log_file=resolve_path(Path(args.log_file)),
        python_bin=args.python_bin,
    )


def main() -> int:
    args = _parse_args()
    config = _config_from_args(args)
    try:
        if args.command == "bootstrap":
            bootstrap_runtime(config)
            return 0
        if args.command == "start":
            start_worker(config, skip_install=args.skip_install, cwd=config.repo_dir)
            return 0
        if args.command == "status":
            status = worker_status(config.pid_file)
            print(status.message)
            return 0 if status.running else 1
        if args.command == "logs":
            for line in read_worker_logs(config.log_file, args.tail):
                print(line)
            return 0
        if args.command == "stop":
            status = stop_worker(config.pid_file)
            print(status.message)
            return 0
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
