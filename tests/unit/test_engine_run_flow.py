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
    engine_artifact_dir = workdir / "engine-artifacts"
    engine_artifact_dir.mkdir()
    engine_artifact_manifest = workdir / "engine-artifacts.manifest.json"
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
                "engine_artifact_dir": str(engine_artifact_dir),
                "engine_artifact_manifest": str(engine_artifact_manifest),
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
        lambda *args, **kwargs: {
            "artifact_uris": {
                "scene": "s3://bucket/jobs/flow-inline/attempt-2/engine/scene.json"
            },
            "engine_manifest_uri": "s3://bucket/jobs/flow-inline/attempt-2/engine-artifacts.json",
            "mlflow_tags_written": True,
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
    assert out["engine_manifest_uri"] == (
        "s3://bucket/jobs/flow-inline/attempt-2/engine-artifacts.json"
    )
    assert out["engine_artifact_uris"] == {
        "scene": "s3://bucket/jobs/flow-inline/attempt-2/engine/scene.json"
    }
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
    engine_artifact_dir = rerun_workdir / "engine-artifacts"
    engine_artifact_dir.mkdir()
    engine_artifact_manifest = rerun_workdir / "engine-artifacts.manifest.json"
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
            "engine_artifact_dir": str(tmp_path / "missing" / "engine-artifacts"),
            "engine_artifact_manifest": str(
                tmp_path / "missing" / "engine-artifacts.manifest.json"
            ),
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
                "engine_artifact_dir": str(engine_artifact_dir),
                "engine_artifact_manifest": str(engine_artifact_manifest),
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
        lambda *args, **kwargs: {
            "artifact_uris": {
                "scene": "s3://bucket/jobs/flow-repo/attempt-1/engine/scene.json"
            },
            "engine_manifest_uri": "s3://bucket/jobs/flow-repo/attempt-1/engine-artifacts.json",
            "mlflow_tags_written": True,
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
    assert out["engine_manifest_uri"] == (
        "s3://bucket/jobs/flow-repo/attempt-1/engine-artifacts.json"
    )


def test_upload_engine_artifacts_task_uploads_manifest_and_writes_mlflow_tags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_module = importlib.import_module("flows.engine_run.tasks")
    artifact_dir = tmp_path / "engine-artifacts"
    artifact_dir.mkdir()
    scene_path = artifact_dir / "scene.json"
    report_path = artifact_dir / "report.json"
    scene_path.write_text('{"scene": true}', encoding="utf-8")
    report_path.write_text('{"ok": true}', encoding="utf-8")
    manifest_path = tmp_path / "engine-artifacts.manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifacts": [
                    {
                        "logical_name": "scene",
                        "relative_path": "scene.json",
                        "mlflow_tag": "artifact_scene_uri",
                    },
                    {
                        "logical_name": "report",
                        "relative_path": "report.json",
                    },
                ],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    stdout_path = tmp_path / "stdout.log"
    stdout_path.write_text('{"mlflow_run_id":"mlflow-123"}\n', encoding="utf-8")
    uploaded_payloads: dict[str, bytes] = {}
    mlflow_calls: list[tuple[str, dict[str, object]]] = []

    def _fake_http_json(
        method: str, url: str, payload: dict[str, object]
    ) -> dict[str, object] | list[dict[str, object]]:
        assert method == "POST"
        if url.endswith("/v1/presign/batch"):
            entries = cast(list[dict[str, object]], payload["entries"])
            return [
                {
                    "kind": "custom",
                    "object_uri": f"s3://bucket/jobs/f1/attempt-1/{entry['filename']}",
                    "url": f"https://storage.example/{entry['filename']}",
                }
                for entry in entries
            ]
        if url.endswith("/v1/presign/put"):
            return {
                "kind": "custom",
                "object_uri": "s3://bucket/jobs/f1/attempt-1/engine-artifacts.json",
                "url": "https://storage.example/engine-artifacts.json",
            }
        raise AssertionError(url)

    def _fake_upload(url: str, payload: bytes) -> None:
        uploaded_payloads[url] = payload

    def _fake_mlflow_post(path: str, payload: dict[str, object]) -> dict[str, object]:
        mlflow_calls.append((path, payload))
        return {}

    monkeypatch.setattr(tasks_module, "http_json", _fake_http_json)
    monkeypatch.setattr(tasks_module, "upload_file", _fake_upload)
    monkeypatch.setattr(tasks_module, "_mlflow_post", _fake_mlflow_post)
    monkeypatch.setenv("STORAGE_API_URL", "https://storage.example")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.example")

    out = tasks_module.upload_engine_artifacts_task.fn(
        {
            "stdout": str(stdout_path),
            "engine_artifact_dir": str(artifact_dir),
            "engine_artifact_manifest": str(manifest_path),
        },
        "f1",
        1,
        0,
    )

    assert out["artifact_uris"] == {
        "scene": "s3://bucket/jobs/f1/attempt-1/engine/scene.json",
        "report": "s3://bucket/jobs/f1/attempt-1/engine/report.json",
    }
    assert (
        out["engine_manifest_uri"]
        == "s3://bucket/jobs/f1/attempt-1/engine-artifacts.json"
    )
    manifest_payload = json.loads(
        uploaded_payloads["https://storage.example/engine-artifacts.json"].decode(
            "utf-8"
        )
    )
    assert manifest_payload["flow_run_id"] == "f1"
    assert manifest_payload["attempt"] == 1
    assert manifest_payload["artifacts"][0]["object_uri"] == (
        "s3://bucket/jobs/f1/attempt-1/engine/scene.json"
    )
    assert mlflow_calls == [
        (
            "/api/2.0/mlflow/runs/set-tag",
            {
                "run_id": "mlflow-123",
                "key": "artifact_engine_manifest_uri",
                "value": "s3://bucket/jobs/f1/attempt-1/engine-artifacts.json",
            },
        ),
        (
            "/api/2.0/mlflow/runs/set-tag",
            {
                "run_id": "mlflow-123",
                "key": "artifact_scene_uri",
                "value": "s3://bucket/jobs/f1/attempt-1/engine/scene.json",
            },
        ),
    ]


def test_upload_engine_artifacts_task_requires_manifest_on_success(
    tmp_path: Path,
) -> None:
    tasks_module = importlib.import_module("flows.engine_run.tasks")
    artifact_dir = tmp_path / "engine-artifacts"
    artifact_dir.mkdir()
    stdout_path = tmp_path / "stdout.log"
    stdout_path.write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError, match="successful engine run must write manifest"):
        tasks_module.upload_engine_artifacts_task.fn(
            {
                "stdout": str(stdout_path),
                "engine_artifact_dir": str(artifact_dir),
                "engine_artifact_manifest": str(
                    tmp_path / "engine-artifacts.manifest.json"
                ),
            },
            "f1",
            1,
            0,
        )
