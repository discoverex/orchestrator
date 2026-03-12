from __future__ import annotations

from datetime import timedelta
from typing import BinaryIO, Protocol


class BucketLike(Protocol):
    name: str


class ObjectLike(Protocol):
    object_name: str | None
    size: int | None
    last_modified: object | None


class GetObjectResponseLike(Protocol):
    def read(self) -> bytes: ...
    def close(self) -> None: ...
    def release_conn(self) -> None: ...


class StatObjectLike(Protocol):
    size: int


class MinioClientProtocol(Protocol):
    def bucket_exists(self, bucket: str) -> bool: ...
    def make_bucket(self, bucket: str) -> None: ...
    def list_buckets(self) -> list[BucketLike]: ...
    def list_objects(
        self,
        *,
        bucket_name: str,
        prefix: str,
        recursive: bool,
        start_after: str | None = None,
    ) -> list[ObjectLike]: ...
    def fput_object(self, bucket: str, object_key: str, file_path: str) -> None: ...
    def put_object(
        self,
        bucket: str,
        object_key: str,
        data: BinaryIO,
        length: int,
        content_type: str,
    ) -> None: ...
    def fget_object(self, bucket: str, object_key: str, file_path: str) -> None: ...
    def get_object(self, bucket: str, object_key: str) -> GetObjectResponseLike: ...
    def stat_object(self, bucket: str, object_key: str) -> StatObjectLike: ...
    def get_presigned_url(
        self, method: str, bucket: str, object_key: str, *, expires: timedelta
    ) -> str: ...
