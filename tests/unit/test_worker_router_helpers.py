from __future__ import annotations

import pytest
from starlette.requests import Request

from worker_router.app import (
    _authorize_storage_request,
    _mlflow_upstream,
    _prefect_upstream,
    _router_is_local_only,
    _storage_host_mode,
)


def _request(host: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/artifact/v1/presign/get",
            "headers": [(b"host", host.encode("ascii"))],
        }
    )


def test_storage_host_mode_distinguishes_machine_human_and_compat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORAGE_API_HOST", "storage-api.discoverex.qzz.io")
    monkeypatch.setenv("STORAGE_HUMAN_HOST", "storage.discoverex.qzz.io")

    assert _storage_host_mode(_request("storage-api.discoverex.qzz.io")) == "machine"
    assert _storage_host_mode(_request("storage.discoverex.qzz.io")) == "human"
    assert _storage_host_mode(_request("legacy.discoverex.qzz.io")) == "compat"


def test_authorize_storage_request_skips_human_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORAGE_HUMAN_HOST", "storage.discoverex.qzz.io")
    monkeypatch.setenv("GATEWAY_REQUIRE_CF_ACCESS", "true")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")

    _authorize_storage_request(
        _request("storage.discoverex.qzz.io"),
        cf_access_client_id=None,
        cf_access_client_secret=None,
    )


def test_mlflow_upstream_includes_internal_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MLFLOW_BACKEND_URL", "http://mlflow:5000/")
    monkeypatch.setenv("MLFLOW_INTERNAL_AUTHORIZATION", "Bearer token")

    upstream = _mlflow_upstream()

    assert upstream.base_url == "http://mlflow:5000"
    assert upstream.headers == {"Authorization": "Bearer token"}


def test_prefect_upstream_reads_remote_prefect_api_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PREFECT_UPSTREAM_URL", "https://prefect.example/api/")

    upstream = _prefect_upstream()

    assert upstream.base_url == "https://prefect.example/api"
    assert upstream.headers == {}


def test_router_is_local_only_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKER_ROUTER_LOCAL_ONLY", raising=False)

    assert _router_is_local_only() is True
