from __future__ import annotations

from tests.integration.storage_gateway.helpers import cf_client, client


def test_rejects_missing_auth() -> None:
    c = client()
    res = c.post(
        "/v1/presign/put", json={"flow_run_id": "f1", "attempt": 1, "kind": "stdout"}
    )
    assert res.status_code == 401


def test_presign_put_builds_attempt_prefix() -> None:
    c = client()
    res = c.post(
        "/v1/presign/put",
        headers={"Authorization": "Bearer test-token"},
        json={"flow_run_id": "f1", "attempt": 2, "kind": "stdout"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert (
        payload["object_uri"]
        == "s3://orchestrator-artifacts/jobs/f1/attempt-2/stdout.log"
    )
    assert payload["url"].startswith("https://gw.example/v1/object/proxy?token=")


def test_ttl_over_limit_returns_400() -> None:
    c = client()
    res = c.post(
        "/v1/presign/get",
        headers={"Authorization": "Bearer test-token"},
        json={"flow_run_id": "f2", "attempt": 1, "kind": "result", "ttl_seconds": 7200},
    )
    assert res.status_code == 400


def test_cf_access_required() -> None:
    c = cf_client()
    res = c.post(
        "/v1/presign/put",
        headers={"Authorization": "Bearer test-token"},
        json={"flow_run_id": "f1", "attempt": 1, "kind": "stdout"},
    )
    assert res.status_code == 403

    ok = c.post(
        "/v1/presign/put",
        headers={
            "Authorization": "Bearer test-token",
            "CF-Access-Client-Id": "cf-id",
            "CF-Access-Client-Secret": "cf-secret",
        },
        json={"flow_run_id": "f1", "attempt": 1, "kind": "stdout"},
    )
    assert ok.status_code == 200
