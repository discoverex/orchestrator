from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

import runner.adapters.outbound.git.runner as git_runner
from runner.adapters.outbound.git.repo import RunnerError


def test_run_raises_runner_error_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git_runner_any = cast(Any, git_runner)

    def _fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args=["git", "status"],
            returncode=1,
            stdout="",
            stderr="boom",
        )

    monkeypatch.setattr(git_runner_any.subprocess, "run", _fake_run)

    with pytest.raises(RunnerError, match="command failed: git status"):
        git_runner._run(["git", "status"])


def test_local_repo_path_handles_file_uri_and_missing_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert git_runner._local_repo_path(repo.as_uri()) == repo
    assert git_runner._local_repo_path(str(tmp_path / "missing")) is None
    assert git_runner._local_repo_path("https://github.com/example/repo.git") is None


def test_prepare_per_repo_venv_skips_without_uv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = {"PATH": os.environ.get("PATH", "")}
    git_runner_any = cast(Any, git_runner)
    monkeypatch.setattr(git_runner_any.shutil, "which", lambda name: None)

    git_runner._prepare_per_repo_venv(tmp_path, env)

    assert "UV_PROJECT_ENVIRONMENT" not in env


def test_prepare_per_repo_venv_skips_when_no_pyproject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = {"PATH": "/usr/bin"}
    git_runner_any = cast(Any, git_runner)
    monkeypatch.setattr(git_runner_any.shutil, "which", lambda name: "/usr/bin/uv")

    git_runner._prepare_per_repo_venv(tmp_path, env)

    assert env["UV_PROJECT_ENVIRONMENT"] == str(tmp_path / ".venv")
    assert env["PATH"].startswith(str(tmp_path / ".venv" / "bin"))


def test_prepare_per_repo_venv_uses_frozen_sync_when_lock_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = {"PATH": "/usr/bin"}
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    calls: list[list[str]] = []

    git_runner_any = cast(Any, git_runner)
    monkeypatch.setattr(git_runner_any.shutil, "which", lambda name: "/usr/bin/uv")

    def _fake_run(
        cmd: list[str], cwd: Path, env: dict[str, str], capture_output: bool, text: bool
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, capture_output, text
        calls.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(git_runner_any.subprocess, "run", _fake_run)

    git_runner._prepare_per_repo_venv(tmp_path, env)

    assert calls == [["/usr/bin/uv", "sync", "--frozen"]]


def test_prepare_per_repo_venv_raises_on_sync_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = {"PATH": "/usr/bin"}
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    git_runner_any = cast(Any, git_runner)
    monkeypatch.setattr(git_runner_any.shutil, "which", lambda name: "/usr/bin/uv")

    def _fake_run(
        cmd: list[str], cwd: Path, env: dict[str, str], capture_output: bool, text: bool
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, capture_output, text
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="", stderr="sync failed"
        )

    monkeypatch.setattr(git_runner_any.subprocess, "run", _fake_run)

    with pytest.raises(RunnerError, match="venv setup failed"):
        git_runner._prepare_per_repo_venv(tmp_path, env)
