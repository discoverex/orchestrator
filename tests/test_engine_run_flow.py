from __future__ import annotations

import importlib
import json
from pathlib import Path

from flows.engine_run_flow import ArtifactLink, upload_outputs_task


def test_upload_outputs_task_skips_already_uploaded(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    uploads: list[Path] = []
    engine_run_flow_module = importlib.import_module("flows.engine_run_flow")

    def _fake_upload(_url: str, path: Path) -> None:
        uploads.append(path)

    monkeypatch.setattr(engine_run_flow_module, "_upload_file", _fake_upload)

    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"
    result = tmp_path / "result.json"
    stdout.write_text("out", encoding="utf-8")
    stderr.write_text("err", encoding="utf-8")
    result.write_text("{}", encoding="utf-8")

    links = [
        ArtifactLink(kind="stdout", object_uri="s3://b/jobs/f1/attempt-1/stdout.log", url="http://example/stdout"),
        ArtifactLink(kind="stderr", object_uri="s3://b/jobs/f1/attempt-1/stderr.log", url="http://example/stderr"),
        ArtifactLink(kind="result", object_uri="s3://b/jobs/f1/attempt-1/result.json", url="http://example/result"),
        ArtifactLink(kind="manifest", object_uri="s3://b/jobs/f1/attempt-1/artifacts.json", url="http://example/manifest"),
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
    manifest_payload = json.loads((tmp_path / "artifacts.json").read_text(encoding="utf-8"))
    assert manifest_payload["flow_run_id"] == "f1"
    assert manifest_payload["attempt"] == 1
    assert {"kind": "stdout", "object_uri": "s3://b/jobs/f1/attempt-1/stdout.log"} in manifest_payload["artifacts"]
