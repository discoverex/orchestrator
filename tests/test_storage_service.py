from __future__ import annotations

import pytest

from storage.domain.services.storage_service import StorageService


class DummyStore:
    def generate_presigned_get(self, object_uri: str, ttl_seconds: int) -> str:
        return f"GET::{object_uri}::{ttl_seconds}"

    def generate_presigned_put(self, object_uri: str, ttl_seconds: int) -> str:
        return f"PUT::{object_uri}::{ttl_seconds}"


def test_build_object_uri() -> None:
    svc = StorageService(DummyStore(), ttl_default=900, ttl_max=3600)
    uri = svc.build_object_uri("bucket-a", "flow-1", 2, "stdout.log")
    assert uri == "s3://bucket-a/jobs/flow-1/attempt-2/stdout.log"


def test_validate_ttl_range() -> None:
    svc = StorageService(DummyStore(), ttl_default=900, ttl_max=3600)
    assert svc.validate_ttl(None) == 900
    assert svc.validate_ttl(120) == 120
    with pytest.raises(ValueError):
        svc.validate_ttl(0)
    with pytest.raises(ValueError):
        svc.validate_ttl(9999)
