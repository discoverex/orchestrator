from __future__ import annotations

from pathlib import Path

import pytest

from runner.adapters.outbound.git.repo import (
    RunnerError,
    repo_cache_root,
    repo_runtime_path,
    repo_runtime_root,
)
from runner.adapters.outbound.git.runner import resolve_commit


def test_resolve_commit_accepts_sha() -> None:
    sha = "a" * 40
    assert resolve_commit("https://example.com/repo.git", sha) == sha


def test_resolve_commit_invalid_ref_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _always_fail(_cmd: list[str], cwd: Path | None = None) -> str:
        _ = cwd
        raise RunnerError("fail")

    monkeypatch.setattr("runner.adapters.outbound.git.runner._run", _always_fail)
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

    monkeypatch.setattr("runner.adapters.outbound.git.runner._run", _fake_run)
    monkeypatch.setattr(
        "runner.adapters.outbound.git.repo.repo_cache_root", lambda: tmp_path / "cache"
    )

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

    monkeypatch.setattr("runner.adapters.outbound.git.runner._run", _fake_run)

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

    monkeypatch.setattr("runner.adapters.outbound.git.runner._run", _fake_run)
    monkeypatch.setattr(
        "runner.adapters.outbound.git.repo.repo_cache_root", lambda: tmp_path / "cache"
    )

    assert resolve_commit(repo_url, "main") == "c" * 40


def test_repo_cache_root_defaults_under_shared_cache_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ORCH_REPO_CACHE_DIR", raising=False)
    monkeypatch.setenv("ORCH_CACHE_DIR", "/tmp/orch-cache")

    assert repo_cache_root() == Path("/tmp/orch-cache/repo")


def test_repo_cache_root_prefers_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORCH_CACHE_DIR", "/tmp/orch-cache")
    monkeypatch.setenv("ORCH_REPO_CACHE_DIR", "/tmp/repos")

    assert repo_cache_root() == Path("/tmp/repos")


def test_repo_runtime_root_defaults_under_worker_runtime_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ORCH_REPO_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("ORCH_WORKER_RUNTIME_DIR", "/var/lib/orchestrator")

    assert repo_runtime_root() == Path("/var/lib/orchestrator/repos")


def test_repo_runtime_root_prefers_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORCH_WORKER_RUNTIME_DIR", "/var/lib/orchestrator")
    monkeypatch.setenv("ORCH_REPO_RUNTIME_DIR", "/srv/orchestrator/repos")

    assert repo_runtime_root() == Path("/srv/orchestrator/repos")


def test_repo_runtime_path_uses_repo_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORCH_REPO_RUNTIME_DIR", "/srv/orchestrator/repos")

    assert repo_runtime_path("https://github.com/discoverex/engine.git") == Path(
        "/srv/orchestrator/repos/discoverex__engine"
    )
