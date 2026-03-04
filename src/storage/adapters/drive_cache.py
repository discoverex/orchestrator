from __future__ import annotations

from pathlib import Path


class DriveCacheStore:
    """Placeholder cache adapter for future Google Drive integration."""

    def get(self, cache_key: str, local_path: str | Path) -> bool:
        _ = (cache_key, local_path)
        return False

    def put(self, cache_key: str, local_path: str | Path) -> None:
        _ = (cache_key, local_path)

    def exists(self, cache_key: str) -> bool:
        _ = cache_key
        return False
