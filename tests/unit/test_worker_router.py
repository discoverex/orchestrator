from __future__ import annotations

import importlib
from urllib import error

from fastapi.testclient import TestClient

from worker_router.app import create_app

worker_router_app_module = importlib.import_module("worker_router.app")


def _client() -> TestClient:
    return TestClient(create_app())


def test_rejects_missing_worker_auth() -> None:
    client = _client()
    res = client.post("/storage/v1/presign/batch", json={})
    assert res.status_code == 401


def test_storage_proxy_injects_downstream_headers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, str] = {}

    class _FakeResponse:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self) -> bytes:
            return b'{"ok": true}'

    def _fake_urlopen(req, timeout=None):  # type: ignore[no-untyped-def]
        _ = timeout
        header_map = {key.lower(): value for key, value in req.header_items()}
        seen["url"] = req.full_url
        seen["authorization"] = header_map.get("authorization")
        seen["cf_id"] = header_map.get("cf-access-client-id")
        return _FakeResponse()

    monkeypatch.setenv("WORKER_ROUTER_TOKEN", "worker-token")
    monkeypatch.setenv("ROUTER_STORAGE_BASE_URL", "http://storage-gateway:8100")
    monkeypatch.setenv("ROUTER_STORAGE_GATEWAY_TOKEN", "storage-token")
    monkeypatch.setenv("ROUTER_STORAGE_CF_ACCESS_CLIENT_ID", "storage-cf-id")
    monkeypatch.setenv("ROUTER_STORAGE_CF_ACCESS_CLIENT_SECRET", "storage-cf-secret")
    monkeypatch.setattr(worker_router_app_module.request, "urlopen", _fake_urlopen)

    client = _client()
    res = client.post(
        "/storage/v1/presign/batch",
        headers={"Authorization": "Bearer worker-token"},
        json={"flow_run_id": "f1", "attempt": 1, "entries": []},
    )
    assert res.status_code == 200
    assert seen == {
        "url": "http://storage-gateway:8100/v1/presign/batch",
        "authorization": "Bearer storage-token",
        "cf_id": "storage-cf-id",
    }


def test_mlflow_proxy_normalizes_network_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _fake_urlopen(_req, timeout=None):  # type: ignore[no-untyped-def]
        _ = timeout
        raise error.URLError("dns failed")

    monkeypatch.setenv("WORKER_ROUTER_TOKEN", "worker-token")
    monkeypatch.setenv("ROUTER_MLFLOW_BASE_URL", "http://mlflow:5000")
    monkeypatch.setattr(worker_router_app_module.request, "urlopen", _fake_urlopen)

    client = _client()
    res = client.get(
        "/mlflow/api/2.0/mlflow/experiments/search",
        headers={"Authorization": "Bearer worker-token"},
    )
    assert res.status_code == 502
    payload = res.json()
    assert payload["upstream"] == "mlflow"
    assert payload["detail"] == "dns failed"
