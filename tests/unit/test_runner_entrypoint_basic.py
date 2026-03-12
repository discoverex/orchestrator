from __future__ import annotations

import pytest

from runner.adapters.outbound.git.runner import cleanup_workdir, run_entrypoint


def test_run_entrypoint_inline_mode_without_repo() -> None:
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
        assert '"run_mode": "inline"' in artifacts.result_path.read_text(
            encoding="utf-8"
        )
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
