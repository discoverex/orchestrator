from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from storage.application.models import ExplorerHeadResult, ExplorerListResult, PresignResult
from storage.domain.models.object_ref import ObjectListEntry, ObjectStat
from storage_gateway.main import app


class DummyStorageApp:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.bucket = "orchestrator-artifacts"

    def _object_uri(self, flow_run_id: str, attempt: int, filename: str) -> str:
        return f"s3://{self.bucket}/jobs/{flow_run_id}/attempt-{attempt}/{filename}"

    def issue_presign(self, *, flow_run_id: str, attempt: int, filename: str, method: str, base_url: str, ttl_seconds: int | None):
        ttl = 900 if ttl_seconds is None else ttl_seconds
        if ttl > 3600:
            raise ValueError("ttl_seconds must be <= 3600")
        object_uri = self._object_uri(flow_run_id, attempt, filename)
        token = f"{method}:{object_uri}"
        return PresignResult(
            object_uri=object_uri,
            url=f"https://gw.example/v1/object/proxy?token={token}",
            expires_at=datetime.now(timezone.utc),
        )

    def issue_batch_put(self, *, entries, base_url: str):
        return [
            self.issue_presign(
                flow_run_id=e.flow_run_id,
                attempt=e.attempt,
                filename=e.filename,
                method="PUT",
                base_url=base_url,
                ttl_seconds=e.ttl_seconds,
            )
            for e in entries
        ]

    def proxy_upload(self, *, token: str, data: bytes, content_type: str):
        method, object_uri = token.split(":", 1)
        assert method == "PUT"
        self.objects[object_uri] = data
        return ObjectStat(uri=object_uri, size=len(data))

    def proxy_download(self, *, token: str) -> bytes:
        method, object_uri = token.split(":", 1)
        assert method == "GET"
        return self.objects[object_uri]

    def head_object(self, object_uri: str):
        if object_uri not in self.objects:
            return ExplorerHeadResult(exists=False, stat=None)
        return ExplorerHeadResult(exists=True, stat=ObjectStat(uri=object_uri, size=len(self.objects[object_uri])))

    def list_buckets(self) -> list[str]:
        return [self.bucket]

    def list_objects(self, *, bucket: str, prefix: str = "", cursor: str | None = None, limit: int = 200):
        rows: list[ObjectListEntry] = []
        for object_uri, data in sorted(self.objects.items()):
            key = object_uri.split("/", 3)[-1]
            if not key.startswith(prefix):
                continue
            if cursor and key <= cursor:
                continue
            rows.append(ObjectListEntry(object_uri=object_uri, object_key=key, size=len(data), last_modified=None))
            if len(rows) >= limit:
                break
        next_cursor = rows[-1].object_key if len(rows) >= limit else None
        return ExplorerListResult(bucket=bucket, prefix=prefix, next_cursor=next_cursor, entries=rows)

    def download_object(self, object_uri: str) -> bytes:
        return self.objects[object_uri]


def _client() -> TestClient:
    app.state.storage_app = DummyStorageApp()
    app.state.token = "test-token"
    app.state.require_cf_access = False
    return TestClient(app)


def _cf_client() -> TestClient:
    app.state.storage_app = DummyStorageApp()
    app.state.token = "test-token"
    app.state.require_cf_access = True
    app.state.cf_client_id = "cf-id"
    app.state.cf_client_secret = "cf-secret"
    return TestClient(app)


def test_rejects_missing_auth() -> None:
    client = _client()
    res = client.post("/v1/presign/put", json={"flow_run_id": "f1", "attempt": 1, "kind": "stdout"})
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
    assert payload["url"].startswith("https://gw.example/v1/object/proxy?token=")


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
    app.state.storage_app.objects["s3://bucket/x/exists.log"] = b"hello-world!!"
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
    assert yes.json() == {"exists": True, "size": 13}
    assert no.status_code == 200
    assert no.json() == {"exists": False, "size": None}


def test_proxy_put_and_get_roundtrip() -> None:
    client = _client()
    put_res = client.post(
        "/v1/presign/put",
        headers={"Authorization": "Bearer test-token"},
        json={"flow_run_id": "f3", "attempt": 1, "kind": "result", "filename": "payload.bin"},
    )
    assert put_res.status_code == 200
    put_url = put_res.json()["url"]
    put_token = parse_qs(urlparse(put_url).query)["token"][0]

    uploaded = client.put(
        f"/v1/object/proxy?token={put_token}",
        content=b"payload-data",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert uploaded.status_code == 200

    get_res = client.post(
        "/v1/presign/get",
        headers={"Authorization": "Bearer test-token"},
        json={"flow_run_id": "f3", "attempt": 1, "kind": "result", "filename": "payload.bin"},
    )
    assert get_res.status_code == 200
    get_token = parse_qs(urlparse(get_res.json()["url"]).query)["token"][0]

    downloaded = client.get(f"/v1/object/proxy?token={get_token}")
    assert downloaded.status_code == 200
    assert downloaded.content == b"payload-data"


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

