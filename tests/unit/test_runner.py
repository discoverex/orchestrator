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


def test_run_entrypoint_merges_job_and_orchestrator_env() -> None:
    artifacts = run_entrypoint(
        repo_url=None,
        resolved_commit=None,
        entrypoint=[
            "/bin/sh",
            "-lc",
            "printf '%s\\n' \"$ORCH_JOB_INPUTS_JSON\" > inputs.json && printf '%s' \"$MLFLOW_TRACKING_URI\"",
        ],
        run_mode="inline",
        env={"MLFLOW_TRACKING_URI": "http://mlflow.example.com"},
        engine="discoverex",
        config_rel_path=None,
        inputs={"contract_version": "v2", "command": "generate"},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-env-check",
    )
    try:
        assert artifacts.exit_code == 0
        assert (
            artifacts.stdout_path.read_text(encoding="utf-8").strip()
            == "http://mlflow.example.com"
        )
        payload = artifacts.workdir / "inputs.json"
        assert '"contract_version": "v2"' in payload.read_text(encoding="utf-8")
    finally:
        cleanup_workdir(artifacts.workdir)
