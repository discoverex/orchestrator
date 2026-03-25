from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

COLAB_DIR = (
    Path(__file__).resolve().parents[2] / "infra" / "stacks" / "worker" / "colab"
)


def _load_module(name: str) -> ModuleType:
    if str(COLAB_DIR) not in sys.path:
        sys.path.insert(0, str(COLAB_DIR))
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def _build_config(runtime_mod: ModuleType, tmp_path: Path) -> Any:
    return runtime_mod.ColabRuntimeConfig(
        repo_dir=tmp_path / "repo",
        cache_root=tmp_path / "cache",
        checkpoint_dir=tmp_path / "checkpoints",
        pid_file=tmp_path / "worker.pid",
        log_file=tmp_path / "worker.log",
        python_bin="python3",
    )


def test_bootstrap_env_sets_pip_and_xdg_cache(tmp_path: Path) -> None:
    bootstrap = _load_module("worker.bootstrap")

    env = bootstrap.bootstrap_env(tmp_path / "cache")

    assert env["PIP_CACHE_DIR"].endswith("/cache/pip")
    assert env["XDG_CACHE_HOME"].endswith("/cache/xdg")


def test_prepare_cache_dirs_creates_shared_cache_subdirs(tmp_path: Path) -> None:
    bootstrap = _load_module("worker.bootstrap")
    cache_root = tmp_path / "cache"

    bootstrap.prepare_cache_dirs(cache_root)

    assert (cache_root / "repo").is_dir()
    assert (cache_root / "models").is_dir()
    assert (cache_root / "pip").is_dir()
    assert (cache_root / "xdg").is_dir()
    assert sorted(path.name for path in cache_root.iterdir()) == [
        "models",
        "pip",
        "repo",
        "xdg",
    ]


def test_bootstrap_runtime_installs_runtime_requirements(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime = _load_module("worker.runtime")
    bootstrap = _load_module("worker.bootstrap")
    config = _build_config(runtime, tmp_path)
    config.repo_dir.mkdir()
    commands: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
        check: bool = True,
        step: str,
    ) -> SimpleNamespace:
        del env, cwd, check, step
        commands.append(cmd)
        return SimpleNamespace(output="ok")

    monkeypatch.setattr(bootstrap, "ensure_drive_mounted", lambda: None)
    monkeypatch.setattr(
        bootstrap,
        "project_runtime_requirements",
        lambda _: ["prefect>=3.0.0", "fastapi>=0.116.0"],
    )
    monkeypatch.setattr(bootstrap, "run_command", fake_run)

    bootstrap.bootstrap_runtime(config)

    assert commands == [
        ["python3", "-m", "pip", "install", "prefect>=3.0.0", "fastapi>=0.116.0"],
        ["python3", "-m", "pip", "show", "prefect"],
        ["python3", "--version"],
    ]
    output = capsys.readouterr().out
    assert f"ready repo={config.repo_dir}" in output
    assert f"ready cache={config.cache_root}" in output
    assert "ready python=python3" in output


def test_project_runtime_requirements_reads_project_dependencies(
    tmp_path: Path,
) -> None:
    bootstrap = _load_module("worker.bootstrap")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "pyproject.toml").write_text(
        """
[project]
dependencies = ["prefect>=3.0.0", "fastapi>=0.116.0"]
""".strip(),
        encoding="utf-8",
    )

    assert bootstrap.project_runtime_requirements(repo_dir) == [
        "prefect>=3.0.0",
        "fastapi>=0.116.0",
    ]


def test_ensure_drive_mounted_requires_drive(monkeypatch: pytest.MonkeyPatch) -> None:
    bootstrap = _load_module("worker.bootstrap")
    monkeypatch.setattr(bootstrap.Path, "exists", lambda self: False)

    with pytest.raises(RuntimeError, match="Google Drive is not mounted"):
        bootstrap.ensure_drive_mounted()
