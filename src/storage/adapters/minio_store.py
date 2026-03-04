from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from storage.domain.models.object_ref import ObjectListEntry, ObjectStat


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError("object URI must start with s3://")
    body = uri[5:]
    parts = body.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("object URI must be s3://bucket/key")
    return parts[0], parts[1]


class MinioObjectStore:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool = False,
        auto_create_bucket: bool = True,
        client: Minio | None = None,
    ) -> None:
        self.client = client or Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self.auto_create_bucket = auto_create_bucket

    def _ensure_bucket(self, bucket: str) -> None:
        if self.auto_create_bucket and not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def list_buckets(self) -> list[str]:
        return sorted(bucket.name for bucket in self.client.list_buckets())

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        start_after: str | None = None,
        limit: int = 200,
    ) -> tuple[list[ObjectListEntry], str | None]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        rows: list[ObjectListEntry] = []
        for item in self.client.list_objects(
            bucket_name=bucket,
            prefix=prefix,
            recursive=False,
            start_after=start_after,
        ):
            key = str(item.object_name)
            rows.append(
                ObjectListEntry(
                    object_uri=f"s3://{bucket}/{key}",
                    object_key=key,
                    size=int(item.size or 0),
                    last_modified=getattr(item, "last_modified", None),
                )
            )
            if len(rows) >= limit:
                break
        next_cursor = rows[-1].object_key if len(rows) >= limit else None
        return rows, next_cursor

    def upload_file(self, local_path: str | Path, object_uri: str) -> ObjectStat:
        bucket, object_key = parse_s3_uri(object_uri)
        self._ensure_bucket(bucket)
        path = Path(local_path)
        size = path.stat().st_size
        self.client.fput_object(bucket, object_key, str(path))
        return ObjectStat(uri=object_uri, size=size)

    def upload_bytes(self, data: bytes, object_uri: str, content_type: str = "application/octet-stream") -> ObjectStat:
        bucket, object_key = parse_s3_uri(object_uri)
        self._ensure_bucket(bucket)
        self.client.put_object(bucket, object_key, BytesIO(data), len(data), content_type=content_type)
        return ObjectStat(uri=object_uri, size=len(data))

    def download_file(self, object_uri: str, local_path: str | Path) -> None:
        bucket, object_key = parse_s3_uri(object_uri)
        self.client.fget_object(bucket, object_key, str(local_path))

    def download_bytes(self, object_uri: str) -> bytes:
        bucket, object_key = parse_s3_uri(object_uri)
        resp = self.client.get_object(bucket, object_key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def exists(self, object_uri: str) -> bool:
        return self.stat(object_uri) is not None

    def stat(self, object_uri: str) -> ObjectStat | None:
        bucket, object_key = parse_s3_uri(object_uri)
        try:
            obj = self.client.stat_object(bucket, object_key)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return None
            raise
        return ObjectStat(uri=object_uri, size=obj.size)

    def generate_presigned_get(self, object_uri: str, ttl_seconds: int) -> str:
        bucket, object_key = parse_s3_uri(object_uri)
        return self.client.get_presigned_url("GET", bucket, object_key, expires=timedelta(seconds=ttl_seconds))

    def generate_presigned_put(self, object_uri: str, ttl_seconds: int) -> str:
        bucket, object_key = parse_s3_uri(object_uri)
        self._ensure_bucket(bucket)
        return self.client.get_presigned_url("PUT", bucket, object_key, expires=timedelta(seconds=ttl_seconds))
