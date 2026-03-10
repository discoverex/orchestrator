from __future__ import annotations

import os

from storage.adapters.minio_store import MinioObjectStore
from storage.application.service import StorageApplicationService


def build_storage_app_from_env() -> StorageApplicationService:
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    store = MinioObjectStore(
        endpoint=os.getenv("MINIO_ENDPOINT", "127.0.0.1:19000"),
        access_key=access_key,
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        auto_create_bucket=os.getenv("MINIO_AUTO_CREATE_BUCKET", "true").lower()
        == "true",
        public_base_url=os.getenv("MINIO_PUBLIC_BASE_URL", ""),
    )
    return StorageApplicationService(
        object_store=store,
        bucket=os.getenv("ARTIFACT_BUCKET", "orchestrator-artifacts"),
        ttl_default=int(os.getenv("PRESIGN_TTL_DEFAULT", "900")),
        ttl_max=int(os.getenv("PRESIGN_TTL_MAX", "3600")),
    )
