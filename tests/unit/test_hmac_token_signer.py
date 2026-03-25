from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo
from typing import Self

import pytest

import storage.adapters.hmac_token_signer as signer_module
from storage.adapters.hmac_token_signer import HmacTokenSigner


def test_mint_and_decode_roundtrip() -> None:
    signer = HmacTokenSigner("secret")

    token = signer.mint("GET", "s3://bucket/path/file.txt", ttl_seconds=60)

    assert signer.decode(token, "GET") == "s3://bucket/path/file.txt"


def test_decode_rejects_tampered_signature() -> None:
    signer = HmacTokenSigner("secret")
    token = signer.mint("GET", "s3://bucket/path/file.txt", ttl_seconds=60)
    payload, signature = token.split(".", 1)
    tampered = f"{payload}.{signature[:-1]}x"

    with pytest.raises(PermissionError, match="invalid token signature"):
        signer.decode(tampered, "GET")


def test_decode_rejects_method_mismatch() -> None:
    signer = HmacTokenSigner("secret")
    token = signer.mint("PUT", "s3://bucket/path/file.txt", ttl_seconds=60)

    with pytest.raises(PermissionError, match="token method mismatch"):
        signer.decode(token, "GET")


def test_decode_rejects_expired_token() -> None:
    signer = HmacTokenSigner("secret")
    base = datetime(2026, 3, 11, tzinfo=UTC)

    class _MintClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            assert tz is UTC
            return cls.fromtimestamp(base.timestamp(), tz=UTC)

    class _DecodeClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            assert tz is UTC
            target = base + timedelta(seconds=2)
            return cls.fromtimestamp(target.timestamp(), tz=UTC)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(signer_module, "datetime", _MintClock)
    token = signer.mint("GET", "s3://bucket/path/file.txt", ttl_seconds=1)
    monkeypatch.setattr(signer_module, "datetime", _DecodeClock)

    try:
        with pytest.raises(PermissionError, match="token expired"):
            signer.decode(token, "GET")
    finally:
        monkeypatch.undo()


def test_decode_rejects_invalid_object_uri() -> None:
    signer = HmacTokenSigner("secret")
    token = signer.mint("GET", "s3://bucket/path/file.txt", ttl_seconds=60)
    payload, signature = token.split(".", 1)
    bad_payload = signer._b64url_encode(b'{"m":"GET","u":"http://bad","e":9999999999}')
    tampered = f"{bad_payload}.{signer._sign(bad_payload)}"
    assert signature

    with pytest.raises(ValueError, match="invalid object uri in token"):
        signer.decode(tampered, "GET")
