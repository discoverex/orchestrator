from __future__ import annotations

from common import StrictModel


class ArtifactLink(StrictModel):
    kind: str
    object_uri: str
    url: str
