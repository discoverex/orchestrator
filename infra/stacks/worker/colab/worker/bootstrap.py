from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .exec import log_step, run_command
from .runtime import ColabRuntimeConfig


@dataclass(frozen=True)
class BootstrapResult:
    repo_dir: Path
    cache_root: Path
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


def project_runtime_requirements(repo_dir: Path) -> list[str]:
    pyproject_path = repo_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return []
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = pyproject.get("project")
    if not isinstance(project, dict):
        return []
    requires = project.get("dependencies")
    if not isinstance(requires, list):
        return []
    return [str(req) for req in requires]


def bootstrap_runtime(config: ColabRuntimeConfig) -> BootstrapResult:
    ensure_drive_mounted()
    ensure_repo_dir(config.repo_dir)
    prepare_cache_dirs(config.cache_root)
    env = bootstrap_env(config.cache_root)
    runtime_deps = project_runtime_requirements(config.repo_dir)
    if runtime_deps:
        run_command(
            [config.python_bin, "-m", "pip", "install", *runtime_deps],
            env=env,
            cwd=config.repo_dir,
            step="bootstrap",
        )
    package_metadata = run_command(
        [config.python_bin, "-m", "pip", "show", "prefect"],
        env=env,
        step="bootstrap",
    ).output.strip()
    python_version = run_command(
        [config.python_bin, "--version"],
        env=env,
        step="bootstrap",
    ).output.strip()
    log_step("bootstrap", f"ready repo={config.repo_dir}")
    log_step("bootstrap", f"ready cache={config.cache_root}")
    log_step("bootstrap", f"ready python={config.python_bin}")
    return BootstrapResult(
        repo_dir=config.repo_dir,
        cache_root=config.cache_root,
        python_version=python_version,
        package_metadata=package_metadata,
    )
