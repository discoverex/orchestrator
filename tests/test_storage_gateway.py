from __future__ import annotations

from fastapi.testclient import TestClient

from storage_gateway.main import app


class DummyStore:
    def stat(self, object_uri: str):
        if object_uri.endswith("exists.log"):
            return type("Stat", (), {"size": 12, "uri": object_uri})
        return None


class DummyStorage:
    object_store = DummyStore()

    def validate_ttl(self, ttl_seconds):
        value = 900 if ttl_seconds is None else ttl_seconds
        if value > 3600:
            raise ValueError("ttl_seconds must be <= 3600")
        return value

    def build_object_uri(self, bucket, flow_run_id, attempt, filename):
        return f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/{filename}"

    def presign_put(self, object_uri, ttl_seconds):
        return f"https://example.local/put?uri={object_uri}&ttl={ttl_seconds}"

    def presign_get(self, object_uri, ttl_seconds):
        return f"https://example.local/get?uri={object_uri}&ttl={ttl_seconds}"


def _client() -> TestClient:
    app.state.storage = DummyStorage()
    app.state.bucket = "orchestrator-artifacts"
    app.state.token = "test-token"
    return TestClient(app)


def _cf_client() -> TestClient:
    app.state.storage = DummyStorage()
    app.state.bucket = "orchestrator-artifacts"
    app.state.token = "test-token"
    app.state.require_cf_access = True
    app.state.cf_client_id = "cf-id"
    app.state.cf_client_secret = "cf-secret"
    return TestClient(app)


def test_rejects_missing_auth() -> None:
    client = _client()
    res = client.post(
        "/v1/presign/put",
        json={"flow_run_id": "f1", "attempt": 1, "kind": "stdout"},
    )
    assert res.status_code == 401


def test_presign_put_builds_attempt_prefix() -> None:
    client = _client()
    res = client.post(
        "/v1/presign/put",
        headers={"Authorization": "Bearer test-token"},
        json={"flow_run_id": "f1", "attempt": 2, "kind": "stdout"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["object_uri"] == "s3://orchestrator-artifacts/jobs/f1/attempt-2/stdout.log"


def test_ttl_over_limit_returns_400() -> None:
    client = _client()
    res = client.post(
        "/v1/presign/get",
        headers={"Authorization": "Bearer test-token"},
        json={"flow_run_id": "f2", "attempt": 1, "kind": "result", "ttl_seconds": 7200},
    )
    assert res.status_code == 400


def test_head_endpoint() -> None:
    client = _client()
    yes = client.post(
        "/v1/object/head",
        headers={"Authorization": "Bearer test-token"},
        json={"object_uri": "s3://bucket/x/exists.log"},
    )
    no = client.post(
        "/v1/object/head",
        headers={"Authorization": "Bearer test-token"},
        json={"object_uri": "s3://bucket/x/missing.log"},
    )
    assert yes.status_code == 200
    assert yes.json() == {"exists": True, "size": 12}
    assert no.status_code == 200
    assert no.json() == {"exists": False, "size": None}


def test_cf_access_required() -> None:
    client = _cf_client()
    res = client.post(
        "/v1/presign/put",
        headers={"Authorization": "Bearer test-token"},
        json={"flow_run_id": "f1", "attempt": 1, "kind": "stdout"},
    )
    assert res.status_code == 403

    ok = client.post(
        "/v1/presign/put",
        headers={
            "Authorization": "Bearer test-token",
            "CF-Access-Client-Id": "cf-id",
            "CF-Access-Client-Secret": "cf-secret",
        },
        json={"flow_run_id": "f1", "attempt": 1, "kind": "stdout"},
    )
    assert ok.status_code == 200
