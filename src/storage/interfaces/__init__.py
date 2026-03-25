"""Boundary package for HTTP/UI interfaces consuming storage.application."""

from storage.interfaces.auth import authorize, authorize_dependency
from storage.interfaces.http import build_artifact_router
from storage.interfaces.http_models import (
    ArtifactKind,
    BatchPresignRequest,
    HeadRequest,
    HeadResponse,
    PresignRequest,
    PresignResponse,
)

__all__ = [
    "ArtifactKind",
    "BatchPresignRequest",
    "HeadRequest",
    "HeadResponse",
    "PresignRequest",
    "PresignResponse",
    "authorize",
    "authorize_dependency",
    "build_artifact_router",
]
