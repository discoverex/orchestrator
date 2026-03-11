from __future__ import annotations

import pytest

from tests.integration.storage_api.helpers import cf_client, client


def test_presign_put_builds_attempt_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch)
    res = c.post(
        "/artifact/v1/presign/put",
        json={"flow_run_id": "f1", "attempt": 2, "kind": "stdout"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert (
        payload["object_uri"]
        == "s3://orchestrator-artifacts/jobs/f1/attempt-2/stdout.log"
    )
    assert payload["url"].startswith("https://object.example/stdout.log")


def test_ttl_over_limit_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch)
    res = c.post(
        "/artifact/v1/presign/get",
        json={"flow_run_id": "f2", "attempt": 1, "kind": "result", "ttl_seconds": 7200},
    )
    assert res.status_code == 400


def test_machine_host_requires_cf_access(monkeypatch: pytest.MonkeyPatch) -> None:
    c = cf_client(monkeypatch)
    res = c.post(
        "/artifact/v1/presign/put",
        headers={"host": "storage-api.discoverex.qzz.io"},
        json={"flow_run_id": "f1", "attempt": 1, "kind": "stdout"},
    )
    assert res.status_code == 403

    ok = c.post(
        "/artifact/v1/presign/put",
        headers={
            "host": "storage-api.discoverex.qzz.io",
            "CF-Access-Client-Id": "cf-id",
            "CF-Access-Client-Secret": "cf-secret",
        },
        json={"flow_run_id": "f1", "attempt": 1, "kind": "stdout"},
    )
    assert ok.status_code == 200


def test_batch_presign_uses_default_filenames(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch)
    res = c.post(
        "/artifact/v1/presign/batch",
        json={
            "flow_run_id": "f1",
            "attempt": 1,
            "entries": [
                {"flow_run_id": "ignored", "attempt": 99, "kind": "stdout"},
                {"flow_run_id": "ignored", "attempt": 99, "kind": "manifest"},
            ],
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload[0]["object_uri"].endswith("/stdout.log")
    assert payload[1]["object_uri"].endswith("/artifacts.json")
