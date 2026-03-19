from __future__ import annotations

import json
from pathlib import Path

from storage.domain.models.object_ref import ObjectRef
from worker_artifacts.uploader import READY_MARKER, UPLOADED_MARKER, run_once


class _FakeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def upload_bytes(
        self,
        *,
        flow_run_id: str,
        attempt: int,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> ObjectRef:
        self.calls.append(
            {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "filename": filename,
                "data": data,
                "content_type": content_type,
            }
        )
        return ObjectRef(
            uri=f"s3://bucket/jobs/{flow_run_id}/attempt-{attempt}/{filename}"
        )


def test_run_once_uploads_ready_directory(tmp_path: Path) -> None:
    root = tmp_path / "engine-artifacts"
    flow_dir = root / "flow-123"
    nested = flow_dir / "scene"
    nested.mkdir(parents=True)
    (nested / "output.json").write_text('{"ok":true}', encoding="utf-8")
    (flow_dir / "stdout.log").write_text("hello", encoding="utf-8")
    (flow_dir / READY_MARKER).write_text("", encoding="utf-8")
    service = _FakeService()

    uploaded = run_once(root=root, service=service)

    assert uploaded == 1
    assert [call["filename"] for call in service.calls] == [
        "engine/scene/output.json",
        "engine/stdout.log",
        "engine-artifacts.json",
    ]
    marker_payload = json.loads(
        (flow_dir / UPLOADED_MARKER).read_text(encoding="utf-8")
    )
    assert marker_payload["flow_run_id"] == "flow-123"
    assert marker_payload["manifest_uri"] == (
        "s3://bucket/jobs/flow-123/attempt-1/engine-artifacts.json"
    )


def test_run_once_skips_directory_until_ready(tmp_path: Path) -> None:
    root = tmp_path / "engine-artifacts"
    flow_dir = root / "flow-456"
    flow_dir.mkdir(parents=True)
    (flow_dir / "result.json").write_text("{}", encoding="utf-8")
    service = _FakeService()

    uploaded = run_once(root=root, service=service)

    assert uploaded == 0
    assert service.calls == []
