from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

import flows.engine_run.flow as flow_module
from flows.engine_run.flow import run_job_flow
from flows.engine_run_flow import ArtifactLink, upload_outputs_task
from flows.job_spec import JobSpec


def test_upload_outputs_task_skips_already_uploaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    uploads: list[Path] = []
    tasks_module = importlib.import_module("flows.engine_run.tasks")

    def _fake_upload(_url: str, payload: bytes) -> None:
        uploads.append(tmp_path / f"payload-{len(payload)}")

    monkeypatch.setattr(tasks_module, "upload_file", _fake_upload)

    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"
    result = tmp_path / "result.json"
    stdout.write_text("out", encoding="utf-8")
    stderr.write_text("err", encoding="utf-8")
    result.write_text("{}", encoding="utf-8")

    links = [
        ArtifactLink(
            kind="stdout",
            object_uri="s3://b/jobs/f1/attempt-1/stdout.log",
            url="http://example/stdout",
        ),
        ArtifactLink(
            kind="stderr",
            object_uri="s3://b/jobs/f1/attempt-1/stderr.log",
            url="http://example/stderr",
        ),
        ArtifactLink(
            kind="result",
            object_uri="s3://b/jobs/f1/attempt-1/result.json",
            url="http://example/result",
        ),
        ArtifactLink(
            kind="manifest",
            object_uri="s3://b/jobs/f1/attempt-1/artifacts.json",
            url="http://example/manifest",
        ),
    ]
    local_paths = {
        "workdir": str(tmp_path),
        "stdout": str(stdout),
        "stderr": str(stderr),
        "result": str(result),
    }

    output = upload_outputs_task.fn(
        links,
        local_paths,
        "f1",
        1,
        already_uploaded={"stdout": "s3://b/jobs/f1/attempt-1/stdout.log"},
    )

    assert output["stdout"] == "s3://b/jobs/f1/attempt-1/stdout.log"
    assert output["stderr"] == "s3://b/jobs/f1/attempt-1/stderr.log"
    assert output["result"] == "s3://b/jobs/f1/attempt-1/result.json"
    assert output["manifest"] == "s3://b/jobs/f1/attempt-1/artifacts.json"

    # stdout skipped, stderr/result/manifest uploaded
    assert len(uploads) == 3
    manifest_payload = json.loads(
        (tmp_path / "artifacts.json").read_text(encoding="utf-8")
    )
    assert manifest_payload["flow_run_id"] == "f1"
    assert manifest_payload["attempt"] == 1
    assert {
        "kind": "stdout",
        "object_uri": "s3://b/jobs/f1/attempt-1/stdout.log",
    } in manifest_payload["artifacts"]


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
    saved_states: list[dict[str, Any]] = []
    cleanup_calls: list[Path] = []

    flow_runtime = cast(Any, flow_module).flow_run
    monkeypatch.setattr(flow_runtime, "get_id", lambda: "flow-inline")
    monkeypatch.setattr(flow_module, "_flow_attempt", lambda: 2)
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
    monkeypatch.setattr(flow_module, "load_checkpoint", lambda path: {})
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

    assert out["flow_run_id"] == "flow-inline"
    assert out["attempt"] == 2
    assert out["run_mode"] == "inline"
    assert out["job_name"] == "inline-job"
    assert out["resolved_commit"] == "inline"
    assert out["outputs_prefix"] == "jobs/flow-inline/attempt-2/"
    assert (
        out["manifest_uri"] == "s3://bucket/jobs/flow-inline/attempt-2/artifacts.json"
    )
    assert cleanup_calls == [workdir]
    assert saved_states[-1]["steps"]["cleanup"] is True


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
    saved_states: list[dict[str, Any]] = []
    rerun_calls: list[dict[str, Any]] = []
    loaded_state = {
        "flow_run_id": "flow-repo",
        "resume_key": "resume-key",
        "resolved_commit": "abc123",
        "steps": {
            "resolve_commit": True,
            "run_entrypoint": True,
            "stdout_uploaded": True,
            "stderr_uploaded": True,
            "result_uploaded": True,
            "manifest_uploaded": True,
        },
        "local_paths": {
            "workdir": str(tmp_path / "missing"),
            "stdout": str(tmp_path / "missing" / "stdout.log"),
            "stderr": str(tmp_path / "missing" / "stderr.log"),
            "result": str(tmp_path / "missing" / "result.json"),
        },
        "uploaded": {"stdout": "s3://bucket/stale"},
        "exit_code": 9,
    }

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
        flow_module, "load_checkpoint", lambda path: deepcopy(loaded_state)
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
    assert saved_states[1]["steps"]["run_entrypoint"] is False
    assert saved_states[1]["uploaded"] == {}
    assert out["stdout_uri"] == "s3://bucket/jobs/flow-repo/attempt-1/stdout.log"
