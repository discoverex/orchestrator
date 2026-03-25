from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest

from storage.adapters.minio_store import MinioObjectStore
from storage.adapters.minio_urls import rewrite_presigned_url
from storage.composition.container import build_storage_app_from_env


@pytest.mark.parametrize(
    "base_url, expected_prefix",
    [
        (
            "https://storage-api.discoverex.qzz.io/storage",
            "https://storage-api.discoverex.qzz.io/storage",
        ),
        (
            "storage-api.discoverex.qzz.io/mlflow",
            "https://storage-api.discoverex.qzz.io/mlflow",
        ),
        ("http://localhost:9000", "http://localhost:9000"),
    ],
)
def test_rewrite_presigned_url_logic(base_url: str, expected_prefix: str) -> None:
    # 순수 URL 재작성 로직 검증
    internal_url = "http://minio:9000/bucket/key?X-Amz-Signature=123"
    rewritten = rewrite_presigned_url(internal_url, base_url)

    assert rewritten.startswith(expected_prefix)
    assert "/bucket/key" in rewritten
    assert "X-Amz-Signature=123" in rewritten
    assert "minio:9000" not in rewritten


def test_presign_url_uses_configured_public_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1. 환경 변수 설정 (외부 도메인)
    expected_domain = "https://storage-api.discoverex.qzz.io/storage"
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "test-key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "test-secret")
    monkeypatch.setenv("MINIO_PUBLIC_BASE_URL", expected_domain)
    monkeypatch.setenv("MINIO_INTERNAL_PRESIGN_BASE_URL", expected_domain)

    # 2. Storage App 초기화
    app = build_storage_app_from_env()

    # MinIO 클라이언트 모킹
    mock_client = MagicMock()
    internal_url = "http://minio:9000/bucket/key?sig=xyz"
    mock_client.get_presigned_url.return_value = internal_url

    store = cast(MinioObjectStore, app.object_store)
    store._client = mock_client

    # 3. GET/PUT URL 발급 및 검증
    url_get = store.generate_presigned_get("s3://bucket/key", 3600)
    url_put = store.generate_presigned_put("s3://bucket/key", 3600)

    for url in [url_get, url_put]:
        assert url.startswith(expected_domain)
        assert "minio:9000" not in url
        assert "/bucket/key" in url


def test_presign_url_fallback_when_no_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # 베이스 URL 환경 변수가 없을 때의 동작 (원본 URL 유지)
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    monkeypatch.delenv("MINIO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("MINIO_INTERNAL_PRESIGN_BASE_URL", raising=False)

    app = build_storage_app_from_env()

    mock_client = MagicMock()
    internal_url = "http://minio:9000/bucket/key?sig=xyz"
    mock_client.get_presigned_url.return_value = internal_url

    store = cast(MinioObjectStore, app.object_store)
    store._client = mock_client

    url_get = store.generate_presigned_get("s3://bucket/key", 3600)
    assert url_get == internal_url
