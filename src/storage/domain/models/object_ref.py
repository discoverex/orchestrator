from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ObjectRef:
    uri: str


@dataclass(frozen=True)
class ObjectStat:
    uri: str
    size: int


@dataclass(frozen=True)
class ObjectListEntry:
    object_uri: str
    object_key: str
    size: int
    last_modified: datetime | None
