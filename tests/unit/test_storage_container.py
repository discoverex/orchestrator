from __future__ import annotations

import pytest

from storage.adapters.minio_store import MinioObjectStore
from storage.application.service import StorageApplicationService
from storage.composition.container import build_storage_app_from_env


def test_build_storage_app_from_env_uses_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "MINIO_ENDPOINT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_SECURE",
        "MINIO_AUTO_CREATE_BUCKET",
        "MINIO_PUBLIC_BASE_URL",
        "MINIO_INTERNAL_PRESIGN_BASE_URL",
        "ARTIFACT_BUCKET",
        "PRESIGN_TTL_DEFAULT",
        "PRESIGN_TTL_MAX",
    ):
        monkeypatch.delenv(name, raising=False)

    app = build_storage_app_from_env()

    assert isinstance(app, StorageApplicationService)
    assert app.bucket == "orchestrator-artifacts"
    assert app.ttl_default == 900
    assert app.ttl_max == 3600
    assert isinstance(app.object_store, MinioObjectStore)
    assert app.object_store.auto_create_bucket is True
    assert app.object_store.public_base_url == ""
    assert app.object_store.internal_presign_base_url == ""


def test_build_storage_app_from_env_applies_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MINIO_ENDPOINT", "minio.internal:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "access")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
    monkeypatch.setenv("MINIO_SECURE", "true")
    monkeypatch.setenv("MINIO_AUTO_CREATE_BUCKET", "false")
    monkeypatch.setenv("MINIO_PUBLIC_BASE_URL", "https://storage.example.com/objects")
    monkeypatch.setenv("MINIO_INTERNAL_PRESIGN_BASE_URL", "http://minio:9000")
    monkeypatch.setenv("ARTIFACT_BUCKET", "custom-bucket")
    monkeypatch.setenv("PRESIGN_TTL_DEFAULT", "120")
    monkeypatch.setenv("PRESIGN_TTL_MAX", "600")

    app = build_storage_app_from_env()

    assert app.bucket == "custom-bucket"
    assert app.ttl_default == 120
    assert app.ttl_max == 600
    assert isinstance(app.object_store, MinioObjectStore)
    assert app.object_store.public_base_url == "https://storage.example.com/objects"
    assert app.object_store.internal_presign_base_url == "http://minio:9000"
    assert app.object_store.auto_create_bucket is False
