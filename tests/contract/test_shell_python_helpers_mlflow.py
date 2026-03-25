from __future__ import annotations

import argparse
import json
from email.message import Message
from pathlib import Path
from urllib import error

import pytest
from scripts.e2e.lib.shell_helpers.commands.mlflow import cmd_verify_engine_mlflow_run


def test_verify_engine_mlflow_run_falls_back_to_experiment_get_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    monkeypatch.setattr(
        "scripts.e2e.lib.shell_helpers.commands.mlflow.http_json", _fake_http_json
    )
    monkeypatch.setattr(
        "scripts.e2e.lib.shell_helpers.mlflow.http_json", _fake_http_json
    )

    args = argparse.Namespace(
        mlflow_tracking_uri="http://mlflow.example",
        log_dir=str(tmp_path),
        cf_access_client_id="",
        cf_access_client_secret="",
    )

    assert cmd_verify_engine_mlflow_run(args) == 0
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
