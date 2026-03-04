from __future__ import annotations

from storage.domain.models.object_ref import ObjectStat
from storage.ports.object_store import ObjectStorePort


class StorageService:
    def __init__(self, object_store: ObjectStorePort, ttl_default: int = 900, ttl_max: int = 3600) -> None:
        self.object_store = object_store
        self.ttl_default = ttl_default
        self.ttl_max = ttl_max

    def validate_ttl(self, ttl_seconds: int | None) -> int:
        value = ttl_seconds if ttl_seconds is not None else self.ttl_default
        if value <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if value > self.ttl_max:
            raise ValueError(f"ttl_seconds must be <= {self.ttl_max}")
        return value

    def build_object_uri(self, bucket: str, flow_run_id: str, attempt: int, filename: str) -> str:
        clean = filename.lstrip("/")
        return f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/{clean}"

    def presign_get(self, object_uri: str, ttl_seconds: int | None = None) -> str:
        ttl = self.validate_ttl(ttl_seconds)
        return self.object_store.generate_presigned_get(object_uri, ttl)

    def presign_put(self, object_uri: str, ttl_seconds: int | None = None) -> str:
        ttl = self.validate_ttl(ttl_seconds)
        return self.object_store.generate_presigned_put(object_uri, ttl)

    def upload_log(self, content: str, object_uri: str) -> ObjectStat:
        return self.object_store.upload_bytes(content.encode("utf-8"), object_uri, content_type="text/plain; charset=utf-8")
