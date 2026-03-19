from __future__ import annotations

import importlib
from urllib import error

import pytest
from fastapi.testclient import TestClient

from tests.integration.storage_api.helpers import DummyStorageApp
from worker_router.app import create_app

worker_router_app_module = importlib.import_module("worker_router.app")


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        worker_router_app_module,
        "build_storage_app_from_env",
        lambda: DummyStorageApp(),
    )
    return TestClient(create_app())


def test_mlflow_proxy_normalizes_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_urlopen(_req: object, timeout: object = None) -> object:
        _ = timeout
        raise error.URLError("dns failed")

    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "worker-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "worker-secret")
    monkeypatch.setenv("MLFLOW_BACKEND_URL", "http://mlflow:5000")
    monkeypatch.setattr(
        worker_router_app_module._proxy_mod.request,
        "urlopen",
        _fake_urlopen,
    )

    client = _client(monkeypatch)
    res = client.get(
        "/mlflow/api/2.0/mlflow/experiments/search",
        headers={
            "CF-Access-Client-Id": "worker-id",
            "CF-Access-Client-Secret": "worker-secret",
        },
    )
    assert res.status_code == 502
    payload = res.json()
    assert payload["upstream"] == "mlflow"
    assert payload["detail"] == "dns failed"


def test_prefect_proxy_normalizes_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_urlopen(_req: object, timeout: object = None) -> object:
        _ = timeout
        raise error.URLError("prefect dns failed")

    monkeypatch.setenv("PREFECT_UPSTREAM_URL", "https://prefect.example/api")
    monkeypatch.setattr(
        worker_router_app_module._proxy_mod.request,
        "urlopen",
        _fake_urlopen,
    )

    client = _client(monkeypatch)
    res = client.get("/prefect/api/flow_runs/filter")
    assert res.status_code == 502
    payload = res.json()
    assert payload["upstream"] == "prefect"
    assert payload["detail"] == "prefect dns failed"
