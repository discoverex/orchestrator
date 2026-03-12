from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from scripts.e2e.lib.shell_helpers.commands.storage import cmd_verify_storage_objects
from scripts.e2e.lib.shell_helpers.http import (
    download_headers,
    rewrite_presigned_url,
)


def test_download_headers_omits_host_when_not_overridden() -> None:
    assert download_headers("") == {}


def test_rewrite_presigned_url_for_internal_loopback_download() -> None:
    rewritten = rewrite_presigned_url(
        "http://127.0.0.1:29000/bucket/object.txt?sig=abc",
        "http://minio:9000",
    )
    assert rewritten == "http://minio:9000/bucket/object.txt?sig=abc"


def test_verify_storage_objects_writes_flow_metadata_in_core_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow_run_id = "flow-123"
    base_uris = {
        "stdout": f"s3://bucket/jobs/{flow_run_id}/attempt-1/stdout.log",
        "stderr": f"s3://bucket/jobs/{flow_run_id}/attempt-1/stderr.log",
        "result": f"s3://bucket/jobs/{flow_run_id}/attempt-1/result.json",
        "manifest": f"s3://bucket/jobs/{flow_run_id}/attempt-1/artifacts.json",
    }
    calls: list[str] = []

    def _fake_http_json(
        method: str,
        url: str,
        *,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 15,
    ) -> dict[str, object]:
        _ = (method, headers, timeout)
        assert payload is not None
        calls.append(url)
        if url.endswith("/v1/object/head"):
            return {"exists": True, "size": 1}
        if url.endswith("/v1/presign/get"):
            kind = str(payload["kind"])
            return {
                "url": f"https://storage.example/{kind}",
                "object_uri": base_uris[kind],
            }
        raise AssertionError(url)

    def _fake_http_text(
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: int = 15,
    ) -> str:
        _ = (headers, timeout)
        if url.endswith("/manifest"):
            return json.dumps(
                {
                    "flow_run_id": flow_run_id,
                    "attempt": 1,
                    "artifacts": [
                        {"kind": "stdout", "object_uri": base_uris["stdout"]},
                        {"kind": "stderr", "object_uri": base_uris["stderr"]},
                        {"kind": "result", "object_uri": base_uris["result"]},
                    ],
                }
            )
        if url.endswith("/result"):
            return json.dumps({"exit_code": 0})
        if url.endswith("/stdout"):
            return '{"status":"ok","scene_id":"scene-1","version_id":"v1"}'
        raise AssertionError(url)

    monkeypatch.setattr(
        "scripts.e2e.lib.shell_helpers.commands.storage.http_json", _fake_http_json
    )
    monkeypatch.setattr(
        "scripts.e2e.lib.shell_helpers.commands.storage.http_text", _fake_http_text
    )

    args = argparse.Namespace(
        flow_run_id=flow_run_id,
        storage_api_url="https://storage.example",
        cf_access_client_id="",
        cf_access_client_secret="",
        artifact_bucket="bucket",
        log_dir=str(tmp_path),
        presigned_host_header="",
        skip_engine_artifacts=True,
        presigned_internal_base_url="",
    )

    assert cmd_verify_storage_objects(args) == 0
    assert (
        json.loads((tmp_path / "flow_uris.json").read_text(encoding="utf-8"))
        == base_uris
    )
    assert calls == ["https://storage.example/artifact/v1/object/head"] * 4
