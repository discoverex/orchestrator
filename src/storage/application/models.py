from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..domain.models.object_ref import ObjectListEntry, ObjectStat


@dataclass(frozen=True)
class PresignResult:
    object_uri: str
    url: str
    expires_at: datetime


@dataclass(frozen=True)
class ExplorerListResult:
    bucket: str
    prefix: str
    next_cursor: str | None
    entries: list[ObjectListEntry]


@dataclass(frozen=True)
class ExplorerHeadResult:
    exists: bool
    stat: ObjectStat | None
