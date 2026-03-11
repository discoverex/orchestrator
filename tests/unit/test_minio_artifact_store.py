from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, cast

import pytest
from minio.error import S3Error

from storage.adapters.minio_store import MinioObjectStore, parse_s3_uri
from storage.domain.models.object_ref import ObjectListEntry


class FakeMinio:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: list[tuple[str, str, bytes]] = []
        self.files: list[tuple[str, str, str]] = []
        self.downloads: list[tuple[str, str, str]] = []
        self.listed_buckets: list[Any] = []
        self.listed_objects: list[Any] = []
        self.stat_result: Any = object()
        self.get_object_response: Any = object()

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def put_object(
        self,
        bucket: str,
        object_key: str,
        data: BinaryIO,
        length: int,
        content_type: str,
    ) -> None:
        _ = content_type
        self.objects.append((bucket, object_key, data.read(length)))

    def list_buckets(self) -> list[Any]:
        return self.listed_buckets

    def list_objects(
        self,
        *,
        bucket_name: str,
        prefix: str,
        recursive: bool,
        start_after: str | None = None,
    ) -> list[Any]:
        _ = (bucket_name, prefix, recursive, start_after)
        return self.listed_objects

    def fput_object(self, bucket: str, object_key: str, file_path: str) -> None:
        self.files.append((bucket, object_key, file_path))

    def fget_object(self, bucket: str, object_key: str, file_path: str) -> None:
        self.downloads.append((bucket, object_key, file_path))

    def get_object(self, bucket: str, object_key: str) -> Any:
        _ = (bucket, object_key)
        return self.get_object_response

    def stat_object(self, bucket: str, object_key: str) -> Any:
        _ = (bucket, object_key)
        if isinstance(self.stat_result, Exception):
            raise self.stat_result
        return self.stat_result

    def get_presigned_url(
        self, method: str, bucket: str, object_key: str, *, expires: object
    ) -> str:
        _ = (method, bucket, object_key, expires)
        return "https://example/presigned"


def test_parse_s3_uri_valid() -> None:
    bucket, key = parse_s3_uri("s3://bucket/path/file.txt")
    assert bucket == "bucket"
    assert key == "path/file.txt"


@pytest.mark.parametrize("uri", ["http://x", "s3://", "s3://bucket", "s3:///key"])
def test_parse_s3_uri_invalid(uri: str) -> None:
    with pytest.raises(ValueError):
        parse_s3_uri(uri)


def test_upload_bytes_autocreate_bucket_and_store_object() -> None:
    fake = FakeMinio()
    store = MinioObjectStore(
        endpoint="127.0.0.1:9000",
        access_key="a",
        secret_key="b",
        auto_create_bucket=True,
        client=fake,
    )
    store.upload_bytes(
        b"hello", "s3://artifacts/jobs/1/stdout.log", content_type="text/plain"
    )

    assert "artifacts" in fake.buckets
    assert fake.objects == [("artifacts", "jobs/1/stdout.log", b"hello")]


def test_presigned_urls_can_split_public_and_internal_bases() -> None:
    store = MinioObjectStore(
        endpoint="127.0.0.1:9000",
        access_key="a",
        secret_key="b",
        public_base_url="https://storage-api.example.com/objects",
        internal_presign_base_url="http://minio:9000",
        client=FakeMinio(),
    )

    put_url = store.generate_presigned_put("s3://artifacts/jobs/1/stdout.log", 60)
    get_url = store.generate_presigned_get("s3://artifacts/jobs/1/stdout.log", 60)

    assert put_url.startswith("http://minio:9000/")
    assert get_url.startswith("https://storage-api.example.com/objects/")


def test_list_buckets_and_objects_are_mapped() -> None:
    fake = FakeMinio()
    fake.listed_buckets = [
        type("Bucket", (), {"name": "b-bucket"})(),
        type("Bucket", (), {"name": "a-bucket"})(),
    ]
    fake.listed_objects = [
        type(
            "Object",
            (),
            {
                "object_name": "jobs/f1/a.txt",
                "size": 3,
                "last_modified": datetime(2026, 3, 11, tzinfo=timezone.utc),
            },
        )(),
        type(
            "Object",
            (),
            {
                "object_name": "jobs/f1/b.txt",
                "size": 4,
                "last_modified": datetime(2026, 3, 12, tzinfo=timezone.utc),
            },
        )(),
    ]
    store = MinioObjectStore(
        endpoint="127.0.0.1:9000",
        access_key="a",
        secret_key="b",
        client=fake,
    )

    buckets = store.list_buckets()
    rows, next_cursor = store.list_objects("artifacts", prefix="jobs/f1/", limit=1)

    assert buckets == ["a-bucket", "b-bucket"]
    assert rows == [
        ObjectListEntry(
            object_uri="s3://artifacts/jobs/f1/a.txt",
            object_key="jobs/f1/a.txt",
            size=3,
            last_modified=datetime(2026, 3, 11, tzinfo=timezone.utc),
        )
    ]
    assert next_cursor == "jobs/f1/a.txt"


def test_list_objects_requires_positive_limit() -> None:
    store = MinioObjectStore(
        endpoint="127.0.0.1:9000",
        access_key="a",
        secret_key="b",
        client=FakeMinio(),
    )

    with pytest.raises(ValueError, match="limit must be > 0"):
        store.list_objects("artifacts", limit=0)


def test_upload_file_and_download_file_roundtrip_paths(tmp_path: Path) -> None:
    fake = FakeMinio()
    store = MinioObjectStore(
        endpoint="127.0.0.1:9000",
        access_key="a",
        secret_key="b",
        client=fake,
    )
    local = tmp_path / "stdout.log"
    local.write_text("hello", encoding="utf-8")
    out = tmp_path / "download.log"

    stat = store.upload_file(local, "s3://artifacts/jobs/1/stdout.log")
    store.download_file("s3://artifacts/jobs/1/stdout.log", out)

    assert stat.uri == "s3://artifacts/jobs/1/stdout.log"
    assert stat.size == 5
    assert fake.files == [("artifacts", "jobs/1/stdout.log", str(local))]
    assert fake.downloads == [("artifacts", "jobs/1/stdout.log", str(out))]


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
    store = MinioObjectStore(
        endpoint="127.0.0.1:9000",
        access_key="a",
        secret_key="b",
        client=FakeMinio(),
    )

    rewritten = store._rewrite_presigned_url(
        "http://minio:9000/bucket/key?x=1",
        "storage.example.com/public",
    )

    assert rewritten == "https://storage.example.com/public/bucket/key?x=1"
