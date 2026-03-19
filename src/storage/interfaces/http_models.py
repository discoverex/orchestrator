from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from common import StrictModel


class ArtifactKind(StrEnum):
    stdout = "stdout"
    stderr = "stderr"
    result = "result"
    manifest = "manifest"
    custom = "custom"


DEFAULT_FILENAMES: dict[ArtifactKind, str] = {
    ArtifactKind.stdout: "stdout.log",
    ArtifactKind.stderr: "stderr.log",
    ArtifactKind.result: "result.json",
    ArtifactKind.manifest: "artifacts.json",
    ArtifactKind.custom: "artifact.bin",
}


class PresignRequest(StrictModel):
    flow_run_id: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    kind: ArtifactKind
    filename: str | None = None
    ttl_seconds: int | None = Field(default=None, gt=0)


class BatchPresignRequest(StrictModel):
    flow_run_id: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    entries: list[PresignRequest] = Field(min_length=1)


class PresignResponse(StrictModel):
    kind: ArtifactKind
    object_uri: str
    url: str
    expires_at: datetime


class HeadRequest(StrictModel):
    object_uri: str


class HeadResponse(StrictModel):
    exists: bool
    size: int | None = None


class UploadFileResponse(StrictModel):
    object_uri: str
    size: int
