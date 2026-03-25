from __future__ import annotations

from typing import Any, BinaryIO


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
