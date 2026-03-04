from __future__ import annotations

import pytest

from storage.adapters.minio_store import MinioObjectStore, parse_s3_uri


class FakeMinio:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: list[tuple[str, str, bytes]] = []

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def put_object(self, bucket: str, object_key: str, data, length: int, content_type: str) -> None:
        self.objects.append((bucket, object_key, data.read(length)))


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
    store.upload_bytes(b"hello", "s3://artifacts/jobs/1/stdout.log", content_type="text/plain")

    assert "artifacts" in fake.buckets
    assert fake.objects == [("artifacts", "jobs/1/stdout.log", b"hello")]
