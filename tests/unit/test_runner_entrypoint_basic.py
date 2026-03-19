from __future__ import annotations

import json

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


def test_run_entrypoint_injects_worker_runtime_cache_defaults(
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
                "printf '%s\\n' \"$ORCH_REPO_CACHE_DIR\" && "
                "printf '%s\\n' \"$ORCH_MODEL_CACHE_DIR\" && "
                "printf '%s\\n' \"$HF_HOME\" && "
                "printf '%s\\n' \"$HF_HUB_CACHE\" && "
                "printf '%s\\n' \"$TRANSFORMERS_CACHE\" && "
                "printf '%s\\n' \"$TORCH_HOME\""
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
            "/var/lib/orchestrator/cache/repo",
            "/var/lib/orchestrator/cache/models",
            "/var/lib/orchestrator/cache/models",
            "/var/lib/orchestrator/cache/models/hub",
            "/var/lib/orchestrator/cache/models/transformers",
            "/var/lib/orchestrator/cache/models/torch",
        ]
    finally:
        cleanup_workdir(artifacts.workdir)


def test_run_entrypoint_uses_explicit_cache_dir_for_repo_and_model_defaults(
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
                "printf '%s\\n' \"$ORCH_REPO_CACHE_DIR\" && "
                "printf '%s\\n' \"$ORCH_MODEL_CACHE_DIR\""
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
            "/tmp/orch-cache/repo",
            "/tmp/orch-cache/models",
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
