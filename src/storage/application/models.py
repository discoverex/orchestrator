from __future__ import annotations

from datetime import datetime

from common import StrictModel

from ..domain.models.object_ref import ObjectListEntry, ObjectStat


class PresignResult(StrictModel):
    object_uri: str
    url: str
    expires_at: datetime


class ExplorerListResult(StrictModel):
    bucket: str
    prefix: str
    next_cursor: str | None
    entries: list[ObjectListEntry]


class ExplorerHeadResult(StrictModel):
    exists: bool
    stat: ObjectStat | None
