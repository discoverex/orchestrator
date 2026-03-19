from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import cast

import pytest


def test_upload_engine_artifacts_task_uploads_manifest_and_writes_mlflow_tags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_module = importlib.import_module("flows.engine_run.task.main")
    artifact_dir = tmp_path / "engine-artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "scene.json").write_text("{}", encoding="utf-8")
    (artifact_dir / "report.json").write_text("{}", encoding="utf-8")
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
            assert payload["flow_run_id"] == "f1"
            assert payload["attempt"] == 1
            assert entries == [
                {
                    "flow_run_id": "f1",
                    "attempt": 1,
                    "kind": "custom",
                    "filename": "engine/scene.json",
                },
                {
                    "flow_run_id": "f1",
                    "attempt": 1,
                    "kind": "custom",
                    "filename": "engine/report.json",
                },
            ]
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

    assert out.artifact_uris == {
        "scene": "s3://bucket/jobs/f1/attempt-1/engine/scene.json",
        "report": "s3://bucket/jobs/f1/attempt-1/engine/report.json",
    }
    assert (
        out.engine_manifest_uri == "s3://bucket/jobs/f1/attempt-1/engine-artifacts.json"
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
    tasks_module = importlib.import_module("flows.engine_run.task.main")
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


def test_upload_engine_artifacts_task_prefers_remote_mlflow_tracking_uri(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_module = importlib.import_module("flows.engine_run.task.main")
    support_module = importlib.import_module("flows.engine_run.task.support")
    artifact_dir = tmp_path / "engine-artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "scene.json").write_text("{}", encoding="utf-8")
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
                    }
                ],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    stdout_path = tmp_path / "stdout.log"
    stdout_path.write_text('{"mlflow_run_id":"mlflow-123"}\n', encoding="utf-8")

    def _fake_http_json(
        method: str, url: str, payload: dict[str, object]
    ) -> dict[str, object] | list[dict[str, object]]:
        assert method == "POST"
        if url.endswith("/v1/presign/batch"):
            return [
                {
                    "kind": "custom",
                    "object_uri": "s3://bucket/jobs/f1/attempt-1/engine/scene.json",
                    "url": "https://storage.example/engine/scene.json",
                }
            ]
        if url.endswith("/v1/presign/put"):
            return {
                "kind": "custom",
                "object_uri": "s3://bucket/jobs/f1/attempt-1/engine-artifacts.json",
                "url": "https://storage.example/engine-artifacts.json",
            }
        raise AssertionError(url)

    def _fake_upload(_url: str, _payload: bytes) -> None:
        return

    def _fake_mlflow_post(path: str, payload: dict[str, object]) -> dict[str, object]:
        assert support_module.mlflow_tracking_uri() == "https://mlflow.discoverex.qzz.io"
        assert path == "/api/2.0/mlflow/runs/set-tag"
        assert payload["run_id"] == "mlflow-123"
        return {}

    monkeypatch.setattr(tasks_module, "http_json", _fake_http_json)
    monkeypatch.setattr(tasks_module, "upload_file", _fake_upload)
    monkeypatch.setattr(tasks_module, "_mlflow_post", _fake_mlflow_post)
    monkeypatch.setenv("STORAGE_API_URL", "https://storage.example")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:38080")
    monkeypatch.setenv(
        "ORCH_REMOTE_MLFLOW_TRACKING_URI", "https://mlflow.discoverex.qzz.io"
    )

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

    assert out.mlflow_tags_written is True
