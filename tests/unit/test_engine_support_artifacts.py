from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request

import pytest

from engine_support.artifacts import upload_artifact_file


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload, ensure_ascii=True).encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _ = exc_type
        _ = exc
        _ = tb


def test_upload_artifact_file_posts_multipart(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "artifact.bin"
    target.write_bytes(b"hello")
    captured: dict[str, object] = {}

    def _fake_urlopen(req: Request, timeout: object = None) -> _Response:
        _ = timeout
        captured["full_url"] = req.full_url
        captured["content_type"] = req.get_header("Content-type")
        captured["body"] = req.data
        captured["flow_run_id"] = req.get_header("X-orch-flow-run-id")
        captured["attempt"] = req.get_header("X-orch-attempt")
        captured["filename"] = req.get_header("X-orch-filename")
        return _Response({"object_uri": "s3://bucket/jobs/f1/attempt-1/a.bin"})

    monkeypatch.setenv("STORAGE_API_URL", "http://127.0.0.1:8200/artifact")
    monkeypatch.setattr("engine_support.artifacts.request.urlopen", _fake_urlopen)

    object_uri = upload_artifact_file(
        flow_run_id="f1",
        attempt=1,
        filename="engine/a.bin",
        local_path=target,
        content_type="application/octet-stream",
    )

    assert object_uri == "s3://bucket/jobs/f1/attempt-1/a.bin"
    assert captured["full_url"] == "http://127.0.0.1:8200/artifact/v1/upload/file"
    assert captured["content_type"] == "application/octet-stream"
    assert captured["flow_run_id"] == "f1"
    assert captured["attempt"] == "1"
    assert captured["filename"] == "engine/a.bin"
    assert captured["body"] == b"hello"


def test_upload_artifact_file_requires_existing_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("STORAGE_API_URL", "http://127.0.0.1:8200")

    with pytest.raises(RuntimeError, match="artifact file not found"):
        upload_artifact_file(
            flow_run_id="f1",
            attempt=1,
            filename="engine/a.bin",
            local_path=tmp_path / "missing.bin",
        )
