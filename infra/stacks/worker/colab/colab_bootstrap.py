from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from colab_exec import log_step, run_command
from colab_runtime import ColabRuntimeConfig


@dataclass(frozen=True)
class BootstrapResult:
    repo_dir: Path
    cache_root: Path
    venv_dir: Path
    python_version: str
    package_metadata: str


def ensure_drive_mounted() -> None:
    if not Path("/content/drive/MyDrive").exists():
        raise RuntimeError(
            "Google Drive is not mounted; run drive.mount('/content/drive') first"
        )


def ensure_repo_dir(repo_dir: Path) -> None:
    if not repo_dir.exists():
        raise RuntimeError(f"repo directory not found: {repo_dir}")
    if not repo_dir.is_dir():
        raise RuntimeError(f"repo path is not a directory: {repo_dir}")


def prepare_cache_dirs(cache_root: Path) -> None:
    for path in (cache_root / "pip", cache_root / "xdg"):
        path.mkdir(parents=True, exist_ok=True)


def bootstrap_env(cache_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PIP_CACHE_DIR"] = str(cache_root / "pip")
    env["XDG_CACHE_HOME"] = str(cache_root / "xdg")
    return env


def recreate_venv(config: ColabRuntimeConfig, env: dict[str, str]) -> Path:
    if config.venv_dir.exists():
        log_step("bootstrap", f"remove existing venv {config.venv_dir}")
        shutil.rmtree(config.venv_dir)
    run_command(
        [config.python_bin, "-m", "venv", str(config.venv_dir)],
        env=env,
        step="bootstrap",
    )
    if not config.venv_python.exists():
        raise RuntimeError(
            f"virtualenv creation failed: {config.venv_python} not found"
        )
    return config.venv_python


def bootstrap_runtime(config: ColabRuntimeConfig) -> BootstrapResult:
    ensure_drive_mounted()
    ensure_repo_dir(config.repo_dir)
    prepare_cache_dirs(config.cache_root)
    env = bootstrap_env(config.cache_root)
    venv_python = recreate_venv(config, env)
    run_command(
        [str(venv_python), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"],
        env=env,
        cwd=config.repo_dir,
        step="bootstrap",
    )
    run_command(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "-e",
            str(config.repo_dir),
            "--no-build-isolation",
            "--use-feature=fast-deps",
        ],
        env=env,
        cwd=config.repo_dir,
        step="bootstrap",
    )
    package_metadata = run_command(
        [str(venv_python), "-m", "pip", "show", "orchestrator"],
        env=env,
        step="bootstrap",
    ).output.strip()
    python_version = run_command(
        [str(venv_python), "--version"],
        env=env,
        step="bootstrap",
    ).output.strip()
    log_step("bootstrap", f"ready repo={config.repo_dir}")
    log_step("bootstrap", f"ready cache={config.cache_root}")
    log_step("bootstrap", f"ready venv={config.venv_dir}")
    return BootstrapResult(
        repo_dir=config.repo_dir,
        cache_root=config.cache_root,
        venv_dir=config.venv_dir,
        python_version=python_version,
        package_metadata=package_metadata,
    )
