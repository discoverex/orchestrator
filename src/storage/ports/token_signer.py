from __future__ import annotations

from typing import Protocol


class TokenSignerPort(Protocol):
    def mint(self, method: str, object_uri: str, ttl_seconds: int) -> str: ...

    def decode(self, token: str, expected_method: str) -> str: ...
