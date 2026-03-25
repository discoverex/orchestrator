from __future__ import annotations

from pathlib import Path

import pytest

from storage.application.service import StorageApplicationService
from storage.domain.models.object_ref import ObjectListEntry, ObjectStat


class DummyStore:
    def generate_presigned_get(self, object_uri: str, ttl_seconds: int) -> str:
        return f"GET::{object_uri}::{ttl_seconds}"

    def generate_presigned_put(self, object_uri: str, ttl_seconds: int) -> str:
        return f"PUT::{object_uri}::{ttl_seconds}"

    def stat(self, object_uri: str) -> ObjectStat | None:
        _ = object_uri
        return None

    def upload_bytes(
        self,
        data: bytes,
        object_uri: str,
        content_type: str = "application/octet-stream",
    ) -> ObjectStat:
        _ = (data, content_type)
        return ObjectStat(uri=object_uri, size=0)

    def download_bytes(self, object_uri: str) -> bytes:
        _ = object_uri
        return b""

    def list_buckets(self) -> list[str]:
        return []

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        start_after: str | None = None,
        limit: int = 200,
    ) -> tuple[list[ObjectListEntry], str | None]:
        _ = (bucket, prefix, start_after, limit)
        return [], None

    def upload_file(self, local_path: str | Path, object_uri: str) -> ObjectStat:
        _ = local_path
        return ObjectStat(uri=object_uri, size=0)

    def download_file(self, object_uri: str, local_path: str | Path) -> None:
        _ = (object_uri, local_path)

    def exists(self, object_uri: str) -> bool:
        _ = object_uri
        return False


def test_build_object_uri() -> None:
    svc = StorageApplicationService(
        DummyStore(), bucket="bucket-a", ttl_default=900, ttl_max=3600
    )
    uri = svc.build_object_uri("flow-1", 2, "stdout.log")
    assert uri == "s3://bucket-a/jobs/flow-1/attempt-2/stdout.log"


def test_validate_ttl_range() -> None:
    svc = StorageApplicationService(
        DummyStore(), bucket="bucket-a", ttl_default=900, ttl_max=3600
    )
    assert svc.validate_ttl(None) == 900
    assert svc.validate_ttl(120) == 120
    with pytest.raises(ValueError):
        svc.validate_ttl(0)
    with pytest.raises(ValueError):
        svc.validate_ttl(9999)


def test_issue_presign_returns_direct_store_url() -> None:
    svc = StorageApplicationService(
        DummyStore(), bucket="bucket-a", ttl_default=900, ttl_max=3600
    )

    put = svc.issue_presign(
        flow_run_id="flow-1",
        attempt=1,
        filename="stdout.log",
        method="PUT",
        ttl_seconds=120,
    )
    get = svc.issue_presign(
        flow_run_id="flow-1",
        attempt=1,
        filename="stdout.log",
        method="GET",
        ttl_seconds=120,
    )

    assert put.url == "PUT::s3://bucket-a/jobs/flow-1/attempt-1/stdout.log::120"
    assert get.url == "GET::s3://bucket-a/jobs/flow-1/attempt-1/stdout.log::120"
