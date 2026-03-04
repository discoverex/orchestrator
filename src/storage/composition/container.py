from __future__ import annotations

import os

from storage.adapters.hmac_token_signer import HmacTokenSigner
from storage.adapters.minio_store import MinioObjectStore
from storage.application.service import StorageApplicationService


def build_storage_app_from_env() -> StorageApplicationService:
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    gateway_token = os.getenv("STORAGE_GATEWAY_TOKEN", "dev-storage-token")
    signer_secret = os.getenv("STORAGE_URL_SIGNING_SECRET", gateway_token)
    store = MinioObjectStore(
        endpoint=os.getenv("MINIO_ENDPOINT", "127.0.0.1:19000"),
        access_key=access_key,
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        auto_create_bucket=os.getenv("MINIO_AUTO_CREATE_BUCKET", "true").lower() == "true",
    )
    signer = HmacTokenSigner(secret=signer_secret)
    return StorageApplicationService(
        object_store=store,
        token_signer=signer,
        bucket=os.getenv("ARTIFACT_BUCKET", "orchestrator-artifacts"),
        ttl_default=int(os.getenv("PRESIGN_TTL_DEFAULT", "900")),
        ttl_max=int(os.getenv("PRESIGN_TTL_MAX", "3600")),
        presign_mode=os.getenv("PRESIGN_MODE", "gateway").lower(),
        public_base_url=os.getenv("STORAGE_PUBLIC_BASE_URL", ""),
    )
