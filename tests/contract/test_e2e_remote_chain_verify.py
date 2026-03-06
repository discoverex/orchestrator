from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "e2e"
        / "verify_remote_chain.py"
    )
    spec = importlib.util.spec_from_file_location("verify_remote_chain", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_e2e_remote_chain__storage_objects__returns_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load_module()
    flow_run_id = "8de7d74e-4728-4a23-859a-5fd3bcc34abb"
    bucket = "orchestrator-artifacts"

    args = argparse.Namespace(
        storage_gateway_url="http://127.0.0.1:8100",
        storage_gateway_token="token",
        artifact_bucket=bucket,
        flow_run_id=flow_run_id,
        attempt=1,
        output_json=str(tmp_path / "storage.json"),
    )

    def _fake_http_json(
        method: str,
        url: str,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> dict[str, object]:
        _ = (payload, headers, timeout)
        if method == "POST" and url.endswith("/v1/object/head"):
            return {"exists": True}
        if method == "POST" and url.endswith("/v1/presign/get"):
            return {"url": "https://presigned/manifest"}
        if method == "GET" and url == "https://presigned/manifest":
            return {
                "flow_run_id": flow_run_id,
                "attempt": 1,
                "artifacts": [
                    {
                        "kind": "stdout",
                        "object_uri": f"s3://{bucket}/jobs/{flow_run_id}/attempt-1/stdout.log",
                    },
                    {
                        "kind": "stderr",
                        "object_uri": f"s3://{bucket}/jobs/{flow_run_id}/attempt-1/stderr.log",
                    },
                    {
                        "kind": "result",
                        "object_uri": f"s3://{bucket}/jobs/{flow_run_id}/attempt-1/result.json",
                    },
                ],
            }
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr(mod, "_http_json", _fake_http_json)
    out = mod._command_storage_objects(args)
    assert out["ok"] is True
    assert Path(args.output_json).exists()


def test_e2e_remote_chain__prune_verify_apply__treats_404_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()

    args = argparse.Namespace(
        prefect_api_url="https://prefect.example.com/api",
        flow_run_id="run-1",
        apply=True,
        ttl_hours=0,
        page_size=200,
        max_runs=1000,
        prefect_cf_access_client_id=None,
        prefect_cf_access_client_secret=None,
    )

    monkeypatch.setattr(mod, "_run_ops_script", lambda *args, **kwargs: {"deleted": 1})

    def _raise_404(*args: object, **kwargs: object) -> dict[str, object]:
        _ = (args, kwargs)
        raise mod.VerifyError("http", "HTTP_404", "not found")

    monkeypatch.setattr(mod, "_http_json", _raise_404)
    out = mod._command_prune_verify(args)
    assert out["ok"] is True
    assert out["apply"] is True
