from __future__ import annotations

from pathlib import Path
from typing import Protocol


class CacheStorePort(Protocol):
    def get(self, cache_key: str, local_path: str | Path) -> bool: ...

    def put(self, cache_key: str, local_path: str | Path) -> None: ...

    def exists(self, cache_key: str) -> bool: ...
