from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

import flows.engine_run.flow as flow_module
from flows.engine_run.flow import run_job_flow
from flows.engine_run.models import ArtifactLink, EngineArtifactsUploadResult, FlowState
from flows.job_spec import JobSpec


def test_run_job_flow_retries_entrypoint_when_artifacts_are_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    rerun_workdir = tmp_path / "rerun"
    rerun_workdir.mkdir()
    stdout = rerun_workdir / "stdout.log"
    stderr = rerun_workdir / "stderr.log"
    result = rerun_workdir / "result.json"
    stdout.write_text("out", encoding="utf-8")
    stderr.write_text("err", encoding="utf-8")
    result.write_text("{}", encoding="utf-8")
    saved_states: list[Any] = []
    rerun_calls: list[dict[str, Any]] = []
    loaded_state = FlowState(
        flow_run_id="flow-repo",
        resume_key="resume-key",
        resolved_commit="abc123",
        steps={
            "resolve_commit": True,
            "run_entrypoint": True,
            "stdout_uploaded": True,
            "stderr_uploaded": True,
            "result_uploaded": True,
            "manifest_uploaded": True,
        },
        local_paths={
            "workdir": str(tmp_path / "missing"),
            "stdout": str(tmp_path / "missing" / "stdout.log"),
            "stderr": str(tmp_path / "missing" / "stderr.log"),
            "result": str(tmp_path / "missing" / "result.json"),
        },
        uploaded={"stdout": "s3://bucket/stale"},
        exit_code=9,
    )

    flow_runtime = cast(Any, flow_module).flow_run
    monkeypatch.setattr(flow_runtime, "get_id", lambda: "flow-repo")
    monkeypatch.setattr(flow_module, "_flow_attempt", lambda: 1)
    monkeypatch.setattr(
        flow_module,
        "parse_job_spec_json",
        lambda raw: JobSpec.model_validate_json(raw),
    )
    monkeypatch.setattr(
        flow_module,
        "resolve_checkpoint_path",
        lambda checkpoint_dir, resume_key: checkpoint_path,
    )
    monkeypatch.setattr(
        flow_module, "load_checkpoint", lambda path, model_cls: deepcopy(loaded_state)
    )
    monkeypatch.setattr(
        flow_module,
        "save_checkpoint",
        lambda path, state: saved_states.append(deepcopy(state)),
    )

    def _run_entrypoint_job_task(**kwargs: Any) -> tuple[dict[str, str], int]:
        rerun_calls.append(kwargs)
        return (
            {
                "workdir": str(rerun_workdir),
                "stdout": str(stdout),
                "stderr": str(stderr),
                "result": str(result),
            },
            0,
        )

    monkeypatch.setattr(
        flow_module, "run_entrypoint_job_task", _run_entrypoint_job_task
    )
    monkeypatch.setattr(
        flow_module,
        "prepare_manifest_task",
        lambda flow_run_id, attempt: [
            ArtifactLink(
                kind="stdout",
                object_uri=f"s3://bucket/jobs/{flow_run_id}/attempt-{attempt}/stdout.log",
                url="https://example/stdout",
            ),
            ArtifactLink(
                kind="stderr",
                object_uri=f"s3://bucket/jobs/{flow_run_id}/attempt-{attempt}/stderr.log",
                url="https://example/stderr",
            ),
            ArtifactLink(
                kind="result",
                object_uri=f"s3://bucket/jobs/{flow_run_id}/attempt-{attempt}/result.json",
                url="https://example/result",
            ),
            ArtifactLink(
                kind="manifest",
                object_uri=f"s3://bucket/jobs/{flow_run_id}/attempt-{attempt}/artifacts.json",
                url="https://example/manifest",
            ),
        ],
    )
    monkeypatch.setattr(
        flow_module,
        "upload_outputs_task",
        lambda *args, **kwargs: {
            "stdout": "s3://bucket/jobs/flow-repo/attempt-1/stdout.log",
            "stderr": "s3://bucket/jobs/flow-repo/attempt-1/stderr.log",
            "result": "s3://bucket/jobs/flow-repo/attempt-1/result.json",
            "manifest": "s3://bucket/jobs/flow-repo/attempt-1/artifacts.json",
        },
    )
    monkeypatch.setattr(
        flow_module,
        "upload_engine_artifacts_task",
        lambda *args, **kwargs: EngineArtifactsUploadResult(
            artifact_uris={},
            engine_manifest_uri="",
            mlflow_tags_written=False,
        ),
    )

    monkeypatch.setattr(flow_module, "cleanup_workdir", lambda path: None)

    out = run_job_flow.fn(
        {
            "run_mode": "repo",
            "engine": "shell",
            "repo_url": "https://github.com/example/repo.git",
            "ref": "main",
            "entrypoint": ["/bin/sh", "-lc", "echo ok"],
            "config": None,
            "inputs": {},
            "env": {},
            "outputs_prefix": None,
        },
        resume_key="resume-key",
        checkpoint_dir=str(tmp_path),
    )

    assert rerun_calls[0]["resolved_commit"] == "abc123"
    assert saved_states[1].is_step_done("run_entrypoint") is False
    assert saved_states[1].uploaded == {}
    assert out.stdout_uri == "s3://bucket/jobs/flow-repo/attempt-1/stdout.log"
