from __future__ import annotations

import json
from types import TracebackType

import pytest

from flows.engine_run import http


def test_gateway_headers_use_cf_service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_API_URL", "https://storage-api.discoverex.qzz.io")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")

    headers = http.gateway_headers()

    assert headers == {
        "Content-Type": "application/json",
        "User-Agent": http.WORKER_HTTP_USER_AGENT,
        "CF-Access-Client-Id": "cf-id",
        "CF-Access-Client-Secret": "cf-secret",
    }


def test_gateway_headers_require_storage_api_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STORAGE_API_URL", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)

    with pytest.raises(
        RuntimeError,
        match="STORAGE_API_URL, CF_ACCESS_CLIENT_ID, CF_ACCESS_CLIENT_SECRET",
    ):
        http.gateway_headers()


def test_storage_base_url_uses_storage_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_API_URL", "https://storage-api.discoverex.qzz.io")

    assert http.storage_base_url() == "https://storage-api.discoverex.qzz.io/artifact"


def test_storage_base_url_requires_storage_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STORAGE_API_URL", raising=False)

    with pytest.raises(RuntimeError, match="STORAGE_API_URL"):
        http.storage_base_url()


def test_http_json_raises_with_response_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORAGE_API_URL", "https://storage-api.discoverex.qzz.io")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")

    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            return None

        def read(self) -> bytes:
            return b"<!DOCTYPE html><html>denied</html>"

    def _fake_urlopen(_req: object) -> _FakeResponse:
        return _FakeResponse()

    monkeypatch.setattr("flows.engine_run.http.request.urlopen", _fake_urlopen)

    with pytest.raises(RuntimeError, match="non-json response from storage API"):
        http.http_json("POST", "https://gateway.example/v1/presign/batch", {"ok": True})


def test_http_json_returns_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_API_URL", "https://storage-api.discoverex.qzz.io")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")
    payload = json.dumps([{"kind": "stdout", "url": "https://example"}]).encode("utf-8")

    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            return None

        def read(self) -> bytes:
            return payload

    def _fake_urlopen(_req: object) -> _FakeResponse:
        return _FakeResponse()

    monkeypatch.setattr("flows.engine_run.http.request.urlopen", _fake_urlopen)

    rows = http.http_json(
        "POST", "https://gateway.example/v1/presign/batch", {"ok": True}
    )

    assert rows == [{"kind": "stdout", "url": "https://example"}]


def test_upload_file_sends_cf_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")
    seen: dict[str, str] = {}

    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            return None

    def _fake_urlopen(req: object) -> _FakeResponse:
        raw_headers = getattr(req, "headers", {})
        headers = {str(key).lower(): str(value) for key, value in raw_headers.items()}
        seen["cf_id"] = headers.get("cf-access-client-id", "")
        seen["cf_secret"] = headers.get("cf-access-client-secret", "")
        return _FakeResponse()

    monkeypatch.setattr("flows.engine_run.http.request.urlopen", _fake_urlopen)

    http.upload_file("https://storage-api.example.com/objects/bucket/key", b"payload")

    assert seen == {"cf_id": "cf-id", "cf_secret": "cf-secret"}
