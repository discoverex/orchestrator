from __future__ import annotations

import os

from storage.adapters.minio_store import MinioObjectStore
from storage.domain.services.storage_service import StorageService


def build_storage_service_from_env() -> StorageService:
    store = MinioObjectStore(
        endpoint=os.getenv("MINIO_ENDPOINT", "127.0.0.1:19000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        auto_create_bucket=os.getenv("MINIO_AUTO_CREATE_BUCKET", "true").lower() == "true",
    )
    return StorageService(
        store,
        ttl_default=int(os.getenv("PRESIGN_TTL_DEFAULT", "900")),
        ttl_max=int(os.getenv("PRESIGN_TTL_MAX", "3600")),
    )
