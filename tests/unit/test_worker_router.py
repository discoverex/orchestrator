from __future__ import annotations

import importlib
from datetime import datetime, timezone
from typing import Any
from urllib import error

import pytest
from fastapi.testclient import TestClient

from storage.application.models import ExplorerHeadResult, PresignResult
from storage.domain.models.object_ref import ObjectStat
from worker_router.app import create_app

worker_router_app_module = importlib.import_module("worker_router.app")


class DummyStorageApp:
    def issue_presign(
        self,
        *,
        flow_run_id: str,
        attempt: int,
        filename: str,
        method: str,
        ttl_seconds: int | None,
    ) -> PresignResult:
        ttl = 900 if ttl_seconds is None else ttl_seconds
        object_uri = f"s3://bucket/jobs/{flow_run_id}/attempt-{attempt}/{filename}"
        return PresignResult(
            object_uri=object_uri,
            url=f"https://object.example/{filename}?method={method}&ttl={ttl}",
            expires_at=datetime.now(timezone.utc),
        )

    def issue_batch_put(self, *, entries: list[Any]) -> list[PresignResult]:
        return [
            self.issue_presign(
                flow_run_id=entry.flow_run_id,
                attempt=entry.attempt,
                filename=entry.filename,
                method="PUT",
                ttl_seconds=entry.ttl_seconds,
            )
            for entry in entries
        ]

    def head_object(self, object_uri: str) -> ExplorerHeadResult:
        return ExplorerHeadResult(
            exists=True,
            stat=ObjectStat(uri=object_uri, size=13),
        )


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        worker_router_app_module,
        "build_storage_app_from_env",
        lambda: DummyStorageApp(),
    )
    return TestClient(create_app())


def test_rejects_missing_storage_service_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATEWAY_REQUIRE_CF_ACCESS", "true")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")
    client = _client(monkeypatch)

    res = client.post(
        "/artifact/v1/presign/batch",
        headers={"host": "storage-api.discoverex.qzz.io"},
        json={
            "flow_run_id": "f1",
            "attempt": 1,
            "entries": [{"flow_run_id": "f1", "attempt": 1, "kind": "stdout"}],
        },
    )

    assert res.status_code == 403


def test_storage_human_host_skips_service_token_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATEWAY_REQUIRE_CF_ACCESS", "true")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")
    monkeypatch.setenv("STORAGE_HUMAN_HOST", "storage.discoverex.qzz.io")
    client = _client(monkeypatch)

    res = client.post(
        "/artifact/v1/presign/get",
        headers={"host": "storage.discoverex.qzz.io"},
        json={"flow_run_id": "f1", "attempt": 1, "kind": "stdout"},
    )

    assert res.status_code == 200
    assert res.json()["url"].startswith("https://object.example/")


def test_storage_compatibility_path_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATEWAY_REQUIRE_CF_ACCESS", "false")
    client = _client(monkeypatch)

    res = client.post(
        "/storage/artifact/v1/presign/batch",
        json={
            "flow_run_id": "f1",
            "attempt": 1,
            "entries": [{"flow_run_id": "f1", "attempt": 1, "kind": "stdout"}],
        },
    )

    assert res.status_code == 200
    assert res.json()[0]["url"].startswith("https://object.example/")


def test_mlflow_proxy_normalizes_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_urlopen(_req: object, timeout: object = None) -> object:
        _ = timeout
        raise error.URLError("dns failed")

    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "worker-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "worker-secret")
    monkeypatch.setenv("MLFLOW_BACKEND_URL", "http://mlflow:5000")
    monkeypatch.setattr(worker_router_app_module.request, "urlopen", _fake_urlopen)

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
