from __future__ import annotations

import logging
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import cast

from minio import Minio
from minio.error import S3Error

from storage.domain.models.object_ref import ObjectListEntry, ObjectStat

from .minio_protocols import MinioClientProtocol
from .minio_urls import parse_s3_uri, rewrite_presigned_url

__all__ = ["MinioObjectStore", "parse_s3_uri"]

logger = logging.getLogger(__name__)


class MinioObjectStore:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool = False,
        auto_create_bucket: bool = True,
        public_base_url: str = "",
        internal_presign_base_url: str = "",
        client: MinioClientProtocol | None = None,
    ) -> None:
        self._client = client or cast(
            MinioClientProtocol,
            Minio(
                endpoint, access_key=access_key, secret_key=secret_key, secure=secure
            ),
        )
        self._auto_create_bucket = auto_create_bucket
        self._public_base_url = public_base_url
        self._internal_presign_base_url = internal_presign_base_url

    def _ensure_bucket(self, bucket: str) -> None:
        if not self._auto_create_bucket:
            return
        try:
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)
        except S3Error:
            pass

    def list_buckets(self) -> list[str]:
        buckets = self._client.list_buckets()
        return [b.name for b in buckets]

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        start_after: str | None = None,
        limit: int = 200,
    ) -> tuple[list[ObjectListEntry], str | None]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        try:
            objects = self._client.list_objects(
                bucket_name=bucket,
                prefix=prefix,
                recursive=True,
                start_after=start_after,
            )
            all_entries = [
                ObjectListEntry(
                    object_uri=f"s3://{bucket}/{obj.object_name}",
                    object_key=obj.object_name,
                    size=obj.size or 0,
                    last_modified=cast("datetime | None", obj.last_modified),
                )
                for obj in objects
                if obj.object_name
            ]
            # Simple pagination slice for mock/wrapper if needed,
            # but minio-py returns iterator
            # Here we just return what we got up to limit
            entries = all_entries[:limit]
            next_cursor = (
                entries[-1].object_key if entries and len(all_entries) > limit else None
            )
            return entries, next_cursor
        except S3Error as exc:
            if exc.code == "NoSuchBucket":
                return [], None
            raise

    def upload_file(self, local_path: str | Path, object_uri: str) -> ObjectStat:
        bucket, key = parse_s3_uri(object_uri)
        self._ensure_bucket(bucket)
        self._client.fput_object(bucket, key, str(local_path))
        return self.stat(object_uri) or ObjectStat(uri=object_uri, size=0)

    def upload_bytes(
        self,
        data: bytes,
        object_uri: str,
        content_type: str = "application/octet-stream",
    ) -> ObjectStat:
        bucket, key = parse_s3_uri(object_uri)
        self._ensure_bucket(bucket)
        self._client.put_object(bucket, key, BytesIO(data), len(data), content_type)
        return ObjectStat(uri=object_uri, size=len(data))

    def download_bytes(self, object_uri: str) -> bytes:
        bucket, key = parse_s3_uri(object_uri)
        resp = self._client.get_object(bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def download_file(self, object_uri: str, local_path: str | Path) -> None:
        bucket, key = parse_s3_uri(object_uri)
        self._client.fget_object(bucket, key, str(local_path))

    def exists(self, object_uri: str) -> bool:
        try:
            return self.stat(object_uri) is not None
        except Exception:
            return False

    def stat(self, object_uri: str) -> ObjectStat | None:
        bucket, key = parse_s3_uri(object_uri)
        try:
            stat = self._client.stat_object(bucket, key)
            return ObjectStat(uri=object_uri, size=stat.size)
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                return None
            raise

    def generate_presigned_get(self, object_uri: str, ttl_seconds: int) -> str:
        bucket, key = parse_s3_uri(object_uri)
        url = self._client.get_presigned_url(
            "GET", bucket, key, expires=timedelta(seconds=ttl_seconds)
        )
        if self._public_base_url:
            return rewrite_presigned_url(url, self._public_base_url)
        return url

    def generate_presigned_put(self, object_uri: str, ttl_seconds: int) -> str:
        bucket, key = parse_s3_uri(object_uri)
        self._ensure_bucket(bucket)
        url = self._client.get_presigned_url(
            "PUT", bucket, key, expires=timedelta(seconds=ttl_seconds)
        )
        if self._internal_presign_base_url:
            return rewrite_presigned_url(url, self._internal_presign_base_url)
        return url
