from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from runner.adapters.outbound.git.runner import cleanup_workdir, run_entrypoint


def test_run_entrypoint_inline_mode_without_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    artifacts = run_entrypoint(
        repo_url=None,
        ref=None,
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
        result = json.loads(artifacts.result_path.read_text(encoding="utf-8"))
        assert result["run_mode"] == "inline"
        assert result["workdir"] == str(artifacts.workdir)
        assert result["stdout_path"] == str(artifacts.stdout_path)
        assert result["stderr_path"] == str(artifacts.stderr_path)
    finally:
        cleanup_workdir(artifacts.workdir)


def test_run_entrypoint_merges_job_and_orchestrator_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    artifacts = run_entrypoint(
        repo_url=None,
        ref=None,
        resolved_commit=None,
        entrypoint=[
            "/bin/sh",
            "-lc",
            (
                "printf '%s\\n' \"$ORCH_JOB_INPUTS_JSON\" > inputs.json && "
                "printf '%s\\n' \"$MLFLOW_TRACKING_URI\" && "
                "printf '%s\\n' \"$ORCH_ENGINE_ARTIFACT_DIR\" > artifact-dir.txt && "
                "printf '%s\\n' \"$ORCH_ENGINE_ARTIFACT_MANIFEST_PATH\" > "
                "artifact-manifest.txt"
            ),
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
        assert '"contract_version": "v2"' in (
            artifacts.workdir / "inputs.json"
        ).read_text(encoding="utf-8")
        assert (artifacts.workdir / "artifact-dir.txt").read_text(
            encoding="utf-8"
        ).strip() == str(artifacts.engine_artifact_dir)
        assert (artifacts.workdir / "artifact-manifest.txt").read_text(
            encoding="utf-8"
        ).strip() == str(artifacts.engine_artifact_manifest_path)
    finally:
        cleanup_workdir(artifacts.workdir)


def test_run_entrypoint_injects_only_parent_worker_runtime_dirs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.setenv("ORCH_WORKER_RUNTIME_DIR", "/var/lib/orchestrator")
    artifacts = run_entrypoint(
        repo_url=None,
        ref=None,
        resolved_commit=None,
        entrypoint=[
            "/bin/sh",
            "-lc",
            (
                "printf '%s\\n' \"$ORCH_WORKER_RUNTIME_DIR\" && "
                "printf '%s\\n' \"$ORCH_CACHE_DIR\" && "
                "printf '%s\\n' \"${ORCH_REPO_CACHE_DIR:-}\" && "
                "printf '%s\\n' \"${ORCH_REPO_RUNTIME_DIR:-}\" && "
                "printf '%s\\n' \"${ORCH_MODEL_CACHE_DIR:-}\" && "
                "printf '%s\\n' \"${ORCHESTRATOR_CHECKPOINT_DIR:-}\" && "
                "printf '%s\\n' \"${HF_HOME:-}\" && "
                "printf '%s\\n' \"${HF_HUB_CACHE:-}\" && "
                "printf '%s\\n' \"${TRANSFORMERS_CACHE:-}\" && "
                "printf '%s\\n' \"${TORCH_HOME:-}\""
            ),
        ],
        run_mode="inline",
        env={},
        engine="discoverex",
        config_rel_path=None,
        inputs={},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-cache-check",
    )
    try:
        assert artifacts.exit_code == 0
        assert artifacts.stdout_path.read_text(encoding="utf-8").splitlines() == [
            "/var/lib/orchestrator",
            "/var/lib/orchestrator/cache",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
    finally:
        cleanup_workdir(artifacts.workdir)


def test_run_entrypoint_preserves_explicit_parent_cache_dir_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("ORCH_WORKER_RUNTIME_DIR", raising=False)
    artifacts = run_entrypoint(
        repo_url=None,
        ref=None,
        resolved_commit=None,
        entrypoint=[
            "/bin/sh",
            "-lc",
            (
                "printf '%s\\n' \"$ORCH_CACHE_DIR\" && "
                "printf '%s\\n' \"${ORCH_REPO_CACHE_DIR:-}\" && "
                "printf '%s\\n' \"${ORCH_REPO_RUNTIME_DIR:-}\" && "
                "printf '%s\\n' \"${ORCH_MODEL_CACHE_DIR:-}\""
            ),
        ],
        run_mode="inline",
        env={"ORCH_CACHE_DIR": "/tmp/orch-cache"},
        engine="discoverex",
        config_rel_path=None,
        inputs={},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-cache-root-check",
    )
    try:
        assert artifacts.exit_code == 0
        assert artifacts.stdout_path.read_text(encoding="utf-8").splitlines() == [
            "/tmp/orch-cache",
            "",
            "",
            "",
        ]
    finally:
        cleanup_workdir(artifacts.workdir)


def test_run_entrypoint_inherits_worker_mlflow_tracking_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://storage-api.example/mlflow")
    artifacts = run_entrypoint(
        repo_url=None,
        ref=None,
        resolved_commit=None,
        entrypoint=["/bin/sh", "-lc", "printf '%s\\n' \"$MLFLOW_TRACKING_URI\""],
        run_mode="inline",
        env={},
        engine="discoverex",
        config_rel_path=None,
        inputs={},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-mlflow-inherit",
    )
    try:
        assert artifacts.exit_code == 0
        assert (
            artifacts.stdout_path.read_text(encoding="utf-8").strip()
            == "https://storage-api.example/mlflow"
        )
    finally:
        cleanup_workdir(artifacts.workdir)


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(["git", *cmd], cwd=cwd, check=True, capture_output=True, text=True)


def test_run_entrypoint_repo_mode_reuses_runtime_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "runtime"
    origin = tmp_path / "origin.git"
    source = tmp_path / "source"
    expected_workdir = runtime_root / "repos" / f"{tmp_path.name}__origin"

    _git(["init", "--bare", str(origin)], cwd=tmp_path)
    source.mkdir()
    _git(["init"], cwd=source)
    _git(["config", "user.name", "Test User"], cwd=source)
    _git(["config", "user.email", "test@example.com"], cwd=source)
    (source / "payload.txt").write_text("v1\n", encoding="utf-8")
    _git(["add", "payload.txt"], cwd=source)
    _git(["commit", "-m", "initial"], cwd=source)
    _git(["branch", "-M", "main"], cwd=source)
    _git(["remote", "add", "origin", str(origin)], cwd=source)
    _git(["push", "-u", "origin", "main"], cwd=source)
    first_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    monkeypatch.setenv("ORCH_WORKER_RUNTIME_DIR", str(runtime_root))

    artifacts = run_entrypoint(
        repo_url=str(origin),
        ref="main",
        resolved_commit=first_commit,
        entrypoint=["/bin/sh", "-lc", "cat payload.txt"],
        run_mode="repo",
        env={},
        engine="discoverex",
        config_rel_path=None,
        inputs={},
        flow_run_id="flow-repo",
        attempt=1,
        outputs_prefix="jobs/flow-repo/attempt-1/",
        job_name="repo-runtime-checkout",
    )
    assert artifacts.exit_code == 0
    assert artifacts.workdir == expected_workdir
    assert artifacts.stdout_path.read_text(encoding="utf-8").strip() == "v1"

    (source / "payload.txt").write_text("v2\n", encoding="utf-8")
    _git(["add", "payload.txt"], cwd=source)
    _git(["commit", "-m", "update"], cwd=source)
    _git(["push", "origin", "main"], cwd=source)
    second_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    reused_artifacts = run_entrypoint(
        repo_url=str(origin),
        ref="main",
        resolved_commit=second_commit,
        entrypoint=["/bin/sh", "-lc", "printf '%s\\n' \"$(cat payload.txt)\""],
        run_mode="repo",
        env={},
        engine="discoverex",
        config_rel_path=None,
        inputs={},
        flow_run_id="flow-repo",
        attempt=2,
        outputs_prefix="jobs/flow-repo/attempt-2/",
        job_name="repo-runtime-checkout",
    )
    try:
        assert reused_artifacts.exit_code == 0
        assert reused_artifacts.workdir == expected_workdir
        assert reused_artifacts.stdout_path.read_text(encoding="utf-8").strip() == "v2"
    finally:
        cleanup_workdir(reused_artifacts.workdir)


def test_run_entrypoint_repo_mode_reuses_runtime_checkout_across_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "runtime"
    origin = tmp_path / "origin.git"
    source = tmp_path / "source"

    _git(["init", "--bare", str(origin)], cwd=tmp_path)
    source.mkdir()
    _git(["init"], cwd=source)
    _git(["config", "user.name", "Test User"], cwd=source)
    _git(["config", "user.email", "test@example.com"], cwd=source)
    (source / "payload.txt").write_text("main\n", encoding="utf-8")
    _git(["add", "payload.txt"], cwd=source)
    _git(["commit", "-m", "main"], cwd=source)
    _git(["branch", "-M", "main"], cwd=source)
    _git(["remote", "add", "origin", str(origin)], cwd=source)
    _git(["push", "-u", "origin", "main"], cwd=source)
    _git(["checkout", "-b", "feature/runtime-branch"], cwd=source)
    (source / "payload.txt").write_text("feature\n", encoding="utf-8")
    _git(["add", "payload.txt"], cwd=source)
    _git(["commit", "-m", "feature"], cwd=source)
    _git(["push", "-u", "origin", "feature/runtime-branch"], cwd=source)
    feature_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    monkeypatch.setenv("ORCH_WORKER_RUNTIME_DIR", str(runtime_root))
    expected_workdir = runtime_root / "repos" / f"{tmp_path.name}__origin"

    feature_artifacts = run_entrypoint(
        repo_url=str(origin),
        ref="feature/runtime-branch",
        resolved_commit=feature_commit,
        entrypoint=["/bin/sh", "-lc", "git branch --show-current && cat payload.txt"],
        run_mode="repo",
        env={},
        engine="discoverex",
        config_rel_path=None,
        inputs={},
        flow_run_id="flow-repo-branches",
        attempt=1,
        outputs_prefix="jobs/flow-repo-branches/attempt-1/",
        job_name="repo-branch-switch",
    )
    assert feature_artifacts.exit_code == 0
    assert feature_artifacts.workdir == expected_workdir
    assert feature_artifacts.stdout_path.read_text(encoding="utf-8").splitlines() == [
        "feature/runtime-branch",
        "feature",
    ]

    _git(["checkout", "main"], cwd=source)
    main_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    main_artifacts = run_entrypoint(
        repo_url=str(origin),
        ref="main",
        resolved_commit=main_commit,
        entrypoint=["/bin/sh", "-lc", "git branch --show-current && cat payload.txt"],
        run_mode="repo",
        env={},
        engine="discoverex",
        config_rel_path=None,
        inputs={},
        flow_run_id="flow-repo-branches",
        attempt=2,
        outputs_prefix="jobs/flow-repo-branches/attempt-2/",
        job_name="repo-branch-switch",
    )
    try:
        assert main_artifacts.exit_code == 0
        assert main_artifacts.workdir == expected_workdir
        assert main_artifacts.stdout_path.read_text(encoding="utf-8").splitlines() == [
            "main",
            "main",
        ]
    finally:
        cleanup_workdir(main_artifacts.workdir)
