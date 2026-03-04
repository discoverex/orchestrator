from __future__ import annotations

from pathlib import Path
from typing import Protocol

from storage.domain.models.object_ref import ObjectListEntry, ObjectStat


class ObjectStorePort(Protocol):
    def list_buckets(self) -> list[str]: ...

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        start_after: str | None = None,
        limit: int = 200,
    ) -> tuple[list[ObjectListEntry], str | None]: ...

    def upload_file(self, local_path: str | Path, object_uri: str) -> ObjectStat: ...

    def upload_bytes(self, data: bytes, object_uri: str, content_type: str = "application/octet-stream") -> ObjectStat: ...

    def download_bytes(self, object_uri: str) -> bytes: ...

    def download_file(self, object_uri: str, local_path: str | Path) -> None: ...

    def exists(self, object_uri: str) -> bool: ...

    def stat(self, object_uri: str) -> ObjectStat | None: ...

    def generate_presigned_get(self, object_uri: str, ttl_seconds: int) -> str: ...

    def generate_presigned_put(self, object_uri: str, ttl_seconds: int) -> str: ...
