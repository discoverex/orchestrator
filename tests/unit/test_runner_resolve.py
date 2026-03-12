from __future__ import annotations

from pathlib import Path

import pytest

from runner.git.repo import RunnerError
from runner.git.runner import resolve_commit


def test_resolve_commit_accepts_sha() -> None:
    sha = "a" * 40
    assert resolve_commit("https://example.com/repo.git", sha) == sha


def test_resolve_commit_invalid_ref_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _always_fail(_cmd: list[str], cwd: Path | None = None) -> str:
        _ = cwd
        raise RunnerError("fail")

    monkeypatch.setattr("runner.git.runner._run", _always_fail)
    with pytest.raises(RunnerError):
        resolve_commit("https://invalid.invalid/repo.git", "main")


def test_resolve_commit_uses_safe_directory_for_local_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo_url = str(repo_path)

    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], cwd: Path | None = None) -> str:
        _ = cwd
        calls.append(cmd)
        if "rev-parse" in cmd:
            return "deadbeef" * 5
        if "ls-remote" in cmd:
            return "deadbeef" * 5 + "\trefs/heads/main"
        return ""

    monkeypatch.setattr("runner.git.runner._run", _fake_run)
    monkeypatch.setattr("runner.git.repo.repo_cache_root", lambda: tmp_path / "cache")

    resolve_commit(repo_url, "main")

    # Should set safe.directory and rev-parse
    assert any("-c" in c and any("safe.directory=" in arg for arg in c) for c in calls)
    assert any("rev-parse" in c for c in calls)


def test_resolve_commit_skips_fetch_if_already_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_url = "https://github.com/user/repo.git"
    sha = "b" * 40

    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], cwd: Path | None = None) -> str:
        _ = cwd
        calls.append(cmd)
        return ""

    monkeypatch.setattr("runner.git.runner._run", _fake_run)

    assert resolve_commit(repo_url, sha) == sha
    assert len(calls) == 0


def test_resolve_commit_handles_github_ssh_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_url = "git@github.com:user/repo.git"
    cached_path = tmp_path / "cache" / "github.com" / "user" / "repo"
    cached_path.mkdir(parents=True)

    def _fake_run(cmd: list[str], cwd: Path | None = None) -> str:
        _ = cwd
        if "rev-parse" in cmd:
            return "c" * 40
        if "ls-remote" in cmd:
            return "c" * 40 + "\trefs/heads/main"
        return ""

    monkeypatch.setattr("runner.git.runner._run", _fake_run)
    monkeypatch.setattr("runner.git.repo.repo_cache_root", lambda: tmp_path / "cache")

    assert resolve_commit(repo_url, "main") == "c" * 40
