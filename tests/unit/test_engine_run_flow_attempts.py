from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

import flows.engine_run.flow as flow_module
from flows.engine_run.flow import run_job_flow
from flows.engine_run.models import ArtifactLink, EngineArtifactsUploadResult
from flows.job_spec import JobSpec


def test_flow_attempt_uses_run_context_run_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        flow_module,
        "get_run_context",
        lambda: type(
            "Ctx", (), {"flow_run": type("FlowRun", (), {"run_count": 3})()}
        )(),
    )

    assert flow_module._flow_attempt() == 3


def test_flow_attempt_defaults_to_one_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> object:
        raise RuntimeError("missing context")

    monkeypatch.setattr(flow_module, "get_run_context", _boom)

    assert flow_module._flow_attempt() == 1


def test_run_job_flow_inline_executes_uploads_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    stdout = workdir / "stdout.log"
    stderr = workdir / "stderr.log"
    result = workdir / "result.json"
    stdout.write_text("out", encoding="utf-8")
    stderr.write_text("err", encoding="utf-8")
    result.write_text("{}", encoding="utf-8")
    saved_states: list[Any] = []
    cleanup_calls: list[Path] = []

    flow_runtime = cast(Any, flow_module).flow_run
    monkeypatch.setattr(flow_runtime, "get_id", lambda: "flow-inline")
    monkeypatch.setattr(flow_module, "_flow_attempt", lambda: 2)
    import json

    monkeypatch.setattr(
        flow_module,
        "parse_job_spec_json",
        lambda raw: JobSpec(**json.loads(raw)),
    )
    monkeypatch.setattr(
        flow_module,
        "resolve_checkpoint_path",
        lambda checkpoint_dir, resume_key: checkpoint_path,
    )
    monkeypatch.setattr(flow_module, "load_checkpoint", lambda path, model_cls: None)
    monkeypatch.setattr(
        flow_module,
        "save_checkpoint",
        lambda path, state: saved_states.append(deepcopy(state)),
    )
    monkeypatch.setattr(
        flow_module,
        "run_entrypoint_job_task",
        lambda **kwargs: (
            {
                "workdir": str(workdir),
                "stdout": str(stdout),
                "stderr": str(stderr),
                "result": str(result),
            },
            0,
        ),
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
            "stdout": "s3://bucket/jobs/flow-inline/attempt-2/stdout.log",
            "stderr": "s3://bucket/jobs/flow-inline/attempt-2/stderr.log",
            "result": "s3://bucket/jobs/flow-inline/attempt-2/result.json",
            "manifest": "s3://bucket/jobs/flow-inline/attempt-2/artifacts.json",
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
    monkeypatch.setattr(
        flow_module, "cleanup_workdir", lambda path: cleanup_calls.append(path)
    )

    out = run_job_flow.fn(
        {
            "run_mode": "inline",
            "engine": "shell",
            "entrypoint": ["/bin/sh", "-lc", "echo ok"],
            "config": None,
            "job_name": "inline-job",
            "inputs": {},
            "env": {},
            "outputs_prefix": None,
        },
        checkpoint_dir=str(tmp_path),
    )

    assert out.flow_run_id == "flow-inline"
    assert out.attempt == 2
    assert out.run_mode == "inline"
    assert out.job_name == "inline-job"
    assert out.resolved_commit == "inline"
    assert out.outputs_prefix == "jobs/flow-inline/attempt-2/"
    assert out.manifest_uri == "s3://bucket/jobs/flow-inline/attempt-2/artifacts.json"
    assert cleanup_calls == [workdir]
    assert saved_states[-1].is_step_done("cleanup") is True
