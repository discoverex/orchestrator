from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactLink:
    kind: str
    object_uri: str
    url: str
