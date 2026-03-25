from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from storage.adapters.minio_store import MinioObjectStore, parse_s3_uri
from storage.domain.models.object_ref import ObjectListEntry
from tests.unit.minio_store_test_support import FakeMinio


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
                "last_modified": datetime(2026, 3, 11, tzinfo=UTC),
            },
        )(),
        type(
            "Object",
            (),
            {
                "object_name": "jobs/f1/b.txt",
                "size": 4,
                "last_modified": datetime(2026, 3, 12, tzinfo=UTC),
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

    assert sorted(buckets) == ["a-bucket", "b-bucket"]
    assert rows == [
        ObjectListEntry(
            object_uri="s3://artifacts/jobs/f1/a.txt",
            object_key="jobs/f1/a.txt",
            size=3,
            last_modified=datetime(2026, 3, 11, tzinfo=UTC),
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
    fake.stat_result = type("Stat", (), {"size": 5})()
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
