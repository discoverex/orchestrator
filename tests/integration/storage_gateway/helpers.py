from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from storage.application.models import (
    ExplorerHeadResult,
    ExplorerListResult,
    PresignResult,
)
from storage.domain.models.object_ref import ObjectListEntry, ObjectStat
from storage_gateway.main import app


class DummyStorageApp:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.bucket = "orchestrator-artifacts"

    def _object_uri(self, flow_run_id: str, attempt: int, filename: str) -> str:
        return f"s3://{self.bucket}/jobs/{flow_run_id}/attempt-{attempt}/{filename}"

    def issue_presign(
        self,
        *,
        flow_run_id: str,
        attempt: int,
        filename: str,
        method: str,
        base_url: str,
        ttl_seconds: int | None,
    ) -> PresignResult:
        _ = base_url
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

    def issue_batch_put(
        self, *, entries: list[Any], base_url: str
    ) -> list[PresignResult]:
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

    def proxy_upload(self, *, token: str, data: bytes, content_type: str) -> ObjectStat:
        _ = content_type
        method, object_uri = token.split(":", 1)
        assert method == "PUT"
        self.objects[object_uri] = data
        return ObjectStat(uri=object_uri, size=len(data))

    def proxy_download(self, *, token: str) -> bytes:
        method, object_uri = token.split(":", 1)
        assert method == "GET"
        return self.objects[object_uri]

    def head_object(self, object_uri: str) -> ExplorerHeadResult:
        if object_uri not in self.objects:
            return ExplorerHeadResult(exists=False, stat=None)
        return ExplorerHeadResult(
            exists=True,
            stat=ObjectStat(uri=object_uri, size=len(self.objects[object_uri])),
        )

    def list_buckets(self) -> list[str]:
        return [self.bucket]

    def list_objects(
        self,
        *,
        bucket: str,
        prefix: str = "",
        cursor: str | None = None,
        limit: int = 200,
    ) -> ExplorerListResult:
        _ = bucket
        rows: list[ObjectListEntry] = []
        for object_uri, data in sorted(self.objects.items()):
            key = object_uri.split("/", 3)[-1]
            if not key.startswith(prefix):
                continue
            if cursor and key <= cursor:
                continue
            rows.append(
                ObjectListEntry(
                    object_uri=object_uri,
                    object_key=key,
                    size=len(data),
                    last_modified=None,
                )
            )
            if len(rows) >= limit:
                break
        next_cursor = rows[-1].object_key if len(rows) >= limit else None
        return ExplorerListResult(
            bucket=bucket, prefix=prefix, next_cursor=next_cursor, entries=rows
        )

    def download_object(self, object_uri: str) -> bytes:
        return self.objects[object_uri]


def client() -> TestClient:
    app.state.storage_app = DummyStorageApp()
    app.state.token = "test-token"
    app.state.require_cf_access = False
    return TestClient(app)


def cf_client() -> TestClient:
    app.state.storage_app = DummyStorageApp()
    app.state.token = "test-token"
    app.state.require_cf_access = True
    app.state.cf_client_id = "cf-id"
    app.state.cf_client_secret = "cf-secret"
    return TestClient(app)
