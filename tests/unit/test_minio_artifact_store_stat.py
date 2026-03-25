from __future__ import annotations

from typing import Any, cast

from minio.error import S3Error

from storage.adapters.minio_store import MinioObjectStore
from storage.adapters.minio_urls import rewrite_presigned_url
from tests.unit.minio_store_test_support import FakeMinio


def test_download_bytes_closes_response() -> None:
    closed: list[str] = []

    class _Response:
        def read(self) -> bytes:
            return b"payload"

        def close(self) -> None:
            closed.append("close")

        def release_conn(self) -> None:
            closed.append("release")

    fake = FakeMinio()
    fake.get_object_response = _Response()
    store = MinioObjectStore(
        endpoint="127.0.0.1:9000",
        access_key="a",
        secret_key="b",
        client=fake,
    )

    assert store.download_bytes("s3://artifacts/jobs/1/stdout.log") == b"payload"
    assert closed == ["close", "release"]


def test_stat_returns_none_for_missing_object() -> None:
    response = cast(
        Any,
        type(
            "Response",
            (),
            {
                "status": 404,
                "reason": "Not Found",
                "headers": {},
                "data": b"",
            },
        )(),
    )
    fake = FakeMinio()
    fake.stat_result = S3Error(
        code="NoSuchKey",
        message="missing",
        resource="/bucket/key",
        request_id="req",
        host_id="host",
        response=response,
    )
    store = MinioObjectStore(
        endpoint="127.0.0.1:9000",
        access_key="a",
        secret_key="b",
        client=fake,
    )

    assert store.stat("s3://artifacts/jobs/1/stdout.log") is None
    assert store.exists("s3://artifacts/jobs/1/stdout.log") is False


def test_stat_returns_object_size_when_present() -> None:
    fake = FakeMinio()
    fake.stat_result = type("Stat", (), {"size": 7})()
    store = MinioObjectStore(
        endpoint="127.0.0.1:9000",
        access_key="a",
        secret_key="b",
        client=fake,
    )

    stat = store.stat("s3://artifacts/jobs/1/stdout.log")

    assert stat is not None
    assert stat.size == 7


def test_rewrite_presigned_url_defaults_to_https_when_scheme_missing() -> None:
    rewritten = rewrite_presigned_url(
        "http://minio:9000/bucket/key?x=1",
        "storage.example.com/public",
    )

    assert rewritten == "https://storage.example.com/public/bucket/key?x=1"
