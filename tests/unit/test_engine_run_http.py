from __future__ import annotations

import json
from pathlib import Path

import pytest

from flows.engine_run import http


def test_gateway_headers_include_cf_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_GATEWAY_TOKEN", "gateway-token")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")

    headers = http.gateway_headers()

    assert headers == {
        "Authorization": "Bearer gateway-token",
        "Content-Type": "application/json",
        "User-Agent": http.WORKER_HTTP_USER_AGENT,
        "CF-Access-Client-Id": "cf-id",
        "CF-Access-Client-Secret": "cf-secret",
    }


def test_gateway_headers_use_worker_router_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_ROUTER_URL", "https://discoverex.qzz.io")
    monkeypatch.setenv("WORKER_ROUTER_TOKEN", "router-token")
    monkeypatch.setenv("STORAGE_GATEWAY_TOKEN", "gateway-token")

    headers = http.gateway_headers()

    assert headers == {
        "Authorization": "Bearer router-token",
        "Content-Type": "application/json",
        "User-Agent": http.WORKER_HTTP_USER_AGENT,
    }


def test_storage_base_url_prefers_worker_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_ROUTER_URL", "https://discoverex.qzz.io")
    monkeypatch.setenv("STORAGE_GATEWAY_URL", "https://storage.example")

    assert http.storage_base_url() == "https://discoverex.qzz.io/storage"


def test_http_json_raises_with_response_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b"<!DOCTYPE html><html>denied</html>"

    def _fake_urlopen(_req: object) -> _FakeResponse:
        return _FakeResponse()

    monkeypatch.setattr(http.request, "urlopen", _fake_urlopen)

    with pytest.raises(RuntimeError, match="non-json response from storage gateway"):
        http.http_json("POST", "https://gateway.example/v1/presign/batch", {"ok": True})


def test_http_json_returns_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps([{"kind": "stdout", "url": "https://example"}]).encode("utf-8")

    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return payload

    def _fake_urlopen(_req: object) -> _FakeResponse:
        return _FakeResponse()

    monkeypatch.setattr(http.request, "urlopen", _fake_urlopen)

    rows = http.http_json("POST", "https://gateway.example/v1/presign/batch", {"ok": True})

    assert rows == [{"kind": "stdout", "url": "https://example"}]
