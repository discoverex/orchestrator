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
