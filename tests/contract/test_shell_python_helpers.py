from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib import error


def _load_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "e2e"
        / "shell_python_helpers.py"
    )
    spec = importlib.util.spec_from_file_location("shell_python_helpers", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_download_headers_omits_host_when_not_overridden() -> None:
    mod = _load_module()

    assert mod._download_headers("") == {}


def test_rewrite_presigned_url_for_internal_loopback_download() -> None:
    mod = _load_module()

    rewritten = mod._rewrite_presigned_url(
        "http://127.0.0.1:29000/bucket/object.txt?sig=abc",
        "http://minio:9000",
    )

    assert rewritten == "http://minio:9000/bucket/object.txt?sig=abc"


def test_verify_storage_objects_writes_flow_metadata_in_core_mode(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    mod = _load_module()
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

    monkeypatch.setattr(mod, "_http_json", _fake_http_json)
    monkeypatch.setattr(mod, "_http_text", _fake_http_text)

    args = argparse.Namespace(
        flow_run_id=flow_run_id,
        storage_api_url="https://storage.example",
        cf_access_client_id="",
        cf_access_client_secret="",
        artifact_bucket="bucket",
        log_dir=str(tmp_path),
        presigned_host_header="",
        skip_engine_artifacts=True,
    )

    assert mod.cmd_verify_storage_objects(args) == 0
    assert (
        json.loads((tmp_path / "flow_uris.json").read_text(encoding="utf-8"))
        == base_uris
    )
    assert calls == ["https://storage.example/artifact/v1/object/head"] * 4
    assert not (tmp_path / "engine_output.json").exists()
    assert not (tmp_path / "engine_uris.json").exists()


def test_verify_engine_mlflow_run_falls_back_to_experiment_get_probe(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    mod = _load_module()
    (tmp_path / "engine_output.json").write_text(
        json.dumps({"scene_id": "scene-1", "version_id": "v1"}, ensure_ascii=True),
        encoding="utf-8",
    )

    calls: list[tuple[str, str]] = []

    def _fake_http_json(
        method: str,
        url: str,
        *,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 15,
    ) -> dict[str, object]:
        _ = (headers, timeout)
        calls.append((method, url))
        if url.endswith("/experiments/get-by-name?experiment_name=discoverex-core"):
            raise error.HTTPError(url, 404, "not found", hdrs=Message(), fp=None)
        if url.endswith("/experiments/search"):
            raise error.HTTPError(url, 404, "not found", hdrs=Message(), fp=None)
        if url.endswith("/experiments/get?experiment_id=0"):
            return {"experiment": {"experiment_id": "0", "name": "Default"}}
        if url.endswith("/experiments/get?experiment_id=1"):
            return {"experiment": {"experiment_id": "1", "name": "discoverex-core"}}
        if url.endswith("/runs/search"):
            assert payload == {
                "experiment_ids": ["1"],
                "max_results": 20,
            }
            return {
                "runs": [
                    {
                        "info": {"run_id": "run-123"},
                        "data": {
                            "params": [
                                {"key": "scene_id", "value": "scene-1"},
                                {"key": "version_id", "value": "v1"},
                            ]
                        },
                    }
                ]
            }
        raise AssertionError((method, url, payload))

    monkeypatch.setattr(mod, "_http_json", _fake_http_json)

    args = argparse.Namespace(
        mlflow_tracking_uri="http://mlflow.example",
        log_dir=str(tmp_path),
        cf_access_client_id="",
        cf_access_client_secret="",
    )

    assert mod.cmd_verify_engine_mlflow_run(args) == 0
    assert json.loads((tmp_path / "mlflow_run.json").read_text(encoding="utf-8")) == {
        "info": {"run_id": "run-123"},
        "data": {
            "params": [
                {"key": "scene_id", "value": "scene-1"},
                {"key": "version_id", "value": "v1"},
            ]
        },
    }
    assert calls[:4] == [
        (
            "GET",
            "http://mlflow.example/api/2.0/mlflow/experiments/get-by-name?experiment_name=discoverex-core",
        ),
        ("POST", "http://mlflow.example/api/2.0/mlflow/experiments/search"),
        ("GET", "http://mlflow.example/api/2.0/mlflow/experiments/get?experiment_id=0"),
        ("GET", "http://mlflow.example/api/2.0/mlflow/experiments/get?experiment_id=1"),
    ]
