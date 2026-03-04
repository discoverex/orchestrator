from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectRef:
    uri: str


@dataclass(frozen=True)
class ObjectStat:
    uri: str
    size: int
