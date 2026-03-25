from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from storage.ports.token_signer import TokenSignerPort


class HmacTokenSigner(TokenSignerPort):
    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("token signing secret must not be empty")
        self._secret = secret.encode("utf-8")

    @staticmethod
    def _b64url_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    @staticmethod
    def _b64url_decode(value: str) -> bytes:
        padded = value + ("=" * (-len(value) % 4))
        return base64.urlsafe_b64decode(padded.encode("ascii"))

    def _sign(self, payload_b64: str) -> str:
        digest = hmac.new(
            self._secret, payload_b64.encode("ascii"), hashlib.sha256
        ).digest()
        return self._b64url_encode(digest)

    def mint(self, method: str, object_uri: str, ttl_seconds: int) -> str:
        exp = int((datetime.now(UTC) + timedelta(seconds=ttl_seconds)).timestamp())
        payload = {"m": method, "u": object_uri, "e": exp}
        payload_b64 = self._b64url_encode(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode(
                "utf-8"
            )
        )
        return f"{payload_b64}.{self._sign(payload_b64)}"

    def decode(self, token: str, expected_method: str) -> str:
        try:
            payload_b64, signature = token.split(".", 1)
        except ValueError as exc:
            raise ValueError("invalid token format") from exc
        if not hmac.compare_digest(signature, self._sign(payload_b64)):
            raise PermissionError("invalid token signature")
        try:
            payload = json.loads(self._b64url_decode(payload_b64).decode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive parse error path
            raise ValueError("invalid token payload") from exc

        if payload.get("m") != expected_method:
            raise PermissionError("token method mismatch")
        expires = int(payload.get("e", 0))
        if int(datetime.now(UTC).timestamp()) > expires:
            raise PermissionError("token expired")
        object_uri = str(payload.get("u", ""))
        if not object_uri.startswith("s3://"):
            raise ValueError("invalid object uri in token")
        return object_uri
