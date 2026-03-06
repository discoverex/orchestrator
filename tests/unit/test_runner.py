from __future__ import annotations

from pathlib import Path

import pytest

from runner import git_runner
from runner.git_runner import RunnerError, cleanup_workdir, resolve_commit, run_entrypoint


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


def test_run_entrypoint_inline_mode_without_repo() -> None:
    artifacts = run_entrypoint(
        repo_url=None,
        resolved_commit=None,
        entrypoint=["/bin/sh", "-lc", "echo inline-ok"],
        run_mode="inline",
        env={},
        engine="shell",
        config_rel_path=None,
        inputs={},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-smoke",
    )
    try:
        assert artifacts.exit_code == 0
        assert artifacts.stdout_path.read_text(encoding="utf-8").strip() == "inline-ok"
        result = artifacts.result_path.read_text(encoding="utf-8")
        assert '"run_mode": "inline"' in result
    finally:
        cleanup_workdir(artifacts.workdir)
