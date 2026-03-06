from __future__ import annotations

from datetime import datetime

from common import StrictModel


class ObjectRef(StrictModel):
    uri: str


class ObjectStat(StrictModel):
    uri: str
    size: int


class ObjectListEntry(StrictModel):
    object_uri: str
    object_key: str
    size: int
    last_modified: datetime | None
