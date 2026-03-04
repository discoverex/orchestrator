from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from storage.main import build_storage_service_from_env


class ArtifactKind(str, Enum):
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


class PresignRequest(BaseModel):
    flow_run_id: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    kind: ArtifactKind
    filename: str | None = None
    ttl_seconds: int | None = Field(default=None, gt=0)


class BatchPresignRequest(BaseModel):
    flow_run_id: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    entries: list[PresignRequest] = Field(min_length=1)


class PresignResponse(BaseModel):
    kind: ArtifactKind
    object_uri: str
    url: str
    expires_at: datetime


class HeadRequest(BaseModel):
    object_uri: str


class HeadResponse(BaseModel):
    exists: bool
    size: int | None = None


app = FastAPI(title="orchestrator-storage-gateway")
app.state.storage = build_storage_service_from_env()
app.state.bucket = os.getenv("ARTIFACT_BUCKET", "orchestrator-artifacts")
app.state.token = os.getenv("STORAGE_GATEWAY_TOKEN", "dev-storage-token")
app.state.require_cf_access = os.getenv("GATEWAY_REQUIRE_CF_ACCESS", "false").lower() in {"1", "true", "yes", "on"}
app.state.cf_client_id = os.getenv("CF_ACCESS_CLIENT_ID", "")
app.state.cf_client_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "")


def _authorize(
    authorization: str | None = Header(default=None),
    cf_access_client_id: str | None = Header(default=None),
    cf_access_client_secret: str | None = Header(default=None),
) -> None:
    expected = f"Bearer {app.state.token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not app.state.require_cf_access:
        return
    if not app.state.cf_client_id or not app.state.cf_client_secret:
        raise HTTPException(status_code=500, detail="cf_access_not_configured")
    if cf_access_client_id != app.state.cf_client_id or cf_access_client_secret != app.state.cf_client_secret:
        raise HTTPException(status_code=403, detail="cf_access_forbidden")


def _filename(req: PresignRequest) -> str:
    return req.filename or DEFAULT_FILENAMES[req.kind]


def _to_response(req: PresignRequest, method: str) -> PresignResponse:
    try:
        ttl = app.state.storage.validate_ttl(req.ttl_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = _filename(req)
    object_uri = app.state.storage.build_object_uri(
        bucket=app.state.bucket,
        flow_run_id=req.flow_run_id,
        attempt=req.attempt,
        filename=filename,
    )
    if method == "PUT":
        url = app.state.storage.presign_put(object_uri, ttl)
    else:
        url = app.state.storage.presign_get(object_uri, ttl)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    return PresignResponse(kind=req.kind, object_uri=object_uri, url=url, expires_at=expires_at)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/presign/put", response_model=PresignResponse, dependencies=[Depends(_authorize)])
def presign_put(req: PresignRequest) -> PresignResponse:
    return _to_response(req, method="PUT")


@app.post("/v1/presign/get", response_model=PresignResponse, dependencies=[Depends(_authorize)])
def presign_get(req: PresignRequest) -> PresignResponse:
    return _to_response(req, method="GET")


@app.post("/v1/presign/batch", response_model=list[PresignResponse], dependencies=[Depends(_authorize)])
def presign_batch(req: BatchPresignRequest) -> list[PresignResponse]:
    out: list[PresignResponse] = []
    for entry in req.entries:
        effective = PresignRequest(
            flow_run_id=req.flow_run_id,
            attempt=req.attempt,
            kind=entry.kind,
            filename=entry.filename,
            ttl_seconds=entry.ttl_seconds,
        )
        out.append(_to_response(effective, method="PUT"))
    return out


@app.post("/v1/object/head", response_model=HeadResponse, dependencies=[Depends(_authorize)])
def head_object(req: HeadRequest) -> HeadResponse:
    stat = app.state.storage.object_store.stat(req.object_uri)
    if stat is None:
        return HeadResponse(exists=False)
    return HeadResponse(exists=True, size=stat.size)
