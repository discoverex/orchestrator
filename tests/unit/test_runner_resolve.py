from __future__ import annotations

from pathlib import Path

import pytest

from runner import git_runner
from runner.git_runner import RunnerError, resolve_commit


def test_resolve_commit_accepts_sha() -> None:
    sha = "a" * 40
    assert resolve_commit("https://example.com/repo.git", sha) == sha


def test_resolve_commit_invalid_ref_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _always_fail(_cmd: list[str], cwd: Path | None = None) -> str:
        _ = cwd
        raise RunnerError("fail")

    monkeypatch.setattr(git_runner, "_run", _always_fail)
    with pytest.raises(RunnerError):
        resolve_commit("https://invalid.invalid/repo.git", "main")


def test_resolve_commit_uses_safe_directory_for_local_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    (tmp_path / ".git").mkdir()

    def _fake_run(cmd: list[str], cwd: Path | None = None) -> str:
        _ = cwd
        calls.append(cmd)
        return "b" * 40

    monkeypatch.setattr(git_runner, "_run", _fake_run)
    out = resolve_commit(str(tmp_path), "HEAD")
    assert out == "b" * 40
    assert calls == [
        [
            "git",
            "-c",
            f"safe.directory={tmp_path.resolve()}",
            "-c",
            f"safe.directory={tmp_path.resolve() / '.git'}",
            "-C",
            str(tmp_path),
            "rev-parse",
            "HEAD",
        ]
    ]


def test_resolve_commit_normalizes_github_ssh_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], cwd: Path | None = None) -> str:
        _ = cwd
        calls.append(cmd)
        return "c" * 40

    monkeypatch.setattr(git_runner, "_run", _fake_run)
    out = resolve_commit("git@github.com:discoverex/engine.git", "dev")
    assert out == "c" * 40
    assert calls == [
        [
            "git",
            "ls-remote",
            "https://github.com/discoverex/engine.git",
            "refs/heads/dev",
        ]
    ]


def test_prepare_cached_repo_removes_broken_cache_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("ORCH_REPO_CACHE_DIR", str(cache_root))
    broken_cache = git_runner._repo_cache_path(
        "https://github.com/discoverex/engine.git"
    )
    broken_cache.mkdir(parents=True)
    calls: list[tuple[list[str], Path | None]] = []

    def _fake_run(cmd: list[str], cwd: Path | None = None) -> str:
        calls.append((cmd, cwd))
        if cmd[:3] == ["git", "clone", "--filter=blob:none"]:
            target = Path(cmd[-1])
            (target / ".git").mkdir(parents=True, exist_ok=True)
        return ""

    monkeypatch.setattr(git_runner, "_run", _fake_run)

    repo = git_runner._prepare_cached_repo(
        "git@github.com:discoverex/engine.git",
        "dev",
        "a" * 40,
    )

    assert repo == broken_cache
    assert (broken_cache / ".git").exists()
    assert calls[0] == (
        [
            "git",
            "clone",
            "--filter=blob:none",
            "https://github.com/discoverex/engine.git",
            str(broken_cache),
        ],
        None,
    )


def test_checkout_target_prefers_named_ref() -> None:
    assert git_runner._checkout_target("dev", "a" * 40) == "dev"
    assert (
        git_runner._checkout_target("refs/tags/v1.0.0", "a" * 40) == "refs/tags/v1.0.0"
    )
    assert git_runner._checkout_target("a" * 40, "b" * 40) == "b" * 40
    assert git_runner._checkout_target(None, "b" * 40) == "b" * 40
