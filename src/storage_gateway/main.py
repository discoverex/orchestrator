from __future__ import annotations

import os
from datetime import datetime
from enum import Enum

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from storage.application.service import PresignEntry
from storage.composition.container import build_storage_app_from_env
from storage_explorer.router import build_explorer_router


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
app.state.storage_app = build_storage_app_from_env()
app.state.token = os.getenv("STORAGE_GATEWAY_TOKEN", "dev-storage-token")
app.state.require_cf_access = os.getenv("GATEWAY_REQUIRE_CF_ACCESS", "false").lower() in {"1", "true", "yes", "on"}
app.state.cf_client_id = os.getenv("CF_ACCESS_CLIENT_ID", "")
app.state.cf_client_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "")
app.state.explorer_enabled = os.getenv("STORAGE_EXPLORER_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
app.state.explorer_local_only = os.getenv("STORAGE_EXPLORER_LOCAL_ONLY", "true").lower() in {"1", "true", "yes", "on"}
app.state.explorer_local_hosts = {
    h.strip() for h in os.getenv("STORAGE_EXPLORER_LOCAL_HOSTS", "127.0.0.1,::1,localhost,testclient").split(",") if h.strip()
}
app.state.explorer_cookie_name = os.getenv("STORAGE_EXPLORER_COOKIE_NAME", "explorer_session")
app.state.explorer_session_ttl = int(os.getenv("STORAGE_EXPLORER_SESSION_TTL", "28800"))
app.state.explorer_page_size = int(os.getenv("STORAGE_EXPLORER_PAGE_SIZE", "200"))
app.state.explorer_sessions: dict[str, datetime] = {}


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


def _to_response(req: PresignRequest, method: str, request: Request) -> PresignResponse:
    try:
        issued = app.state.storage_app.issue_presign(
            flow_run_id=req.flow_run_id,
            attempt=req.attempt,
            filename=_filename(req),
            method=method,
            base_url=str(request.base_url),
            ttl_seconds=req.ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PresignResponse(kind=req.kind, object_uri=issued.object_uri, url=issued.url, expires_at=issued.expires_at)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/presign/put", response_model=PresignResponse, dependencies=[Depends(_authorize)])
def presign_put(req: PresignRequest, request: Request) -> PresignResponse:
    return _to_response(req, method="PUT", request=request)


@app.post("/v1/presign/get", response_model=PresignResponse, dependencies=[Depends(_authorize)])
def presign_get(req: PresignRequest, request: Request) -> PresignResponse:
    return _to_response(req, method="GET", request=request)


@app.post("/v1/presign/batch", response_model=list[PresignResponse], dependencies=[Depends(_authorize)])
def presign_batch(req: BatchPresignRequest, request: Request) -> list[PresignResponse]:
    entries = [
        PresignEntry(
            flow_run_id=req.flow_run_id,
            attempt=req.attempt,
            kind=e.kind.value,
            filename=_filename(e),
            ttl_seconds=e.ttl_seconds,
        )
        for e in req.entries
    ]
    try:
        rows = app.state.storage_app.issue_batch_put(entries=entries, base_url=str(request.base_url))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return [
        PresignResponse(
            kind=req.entries[i].kind,
            object_uri=row.object_uri,
            url=row.url,
            expires_at=row.expires_at,
        )
        for i, row in enumerate(rows)
    ]


@app.put("/v1/object/proxy")
async def proxy_put(request: Request, token: str = Query(min_length=10)) -> dict[str, str]:
    body = await request.body()
    content_type = request.headers.get("content-type", "application/octet-stream")
    try:
        app.state.storage_app.proxy_upload(token=token, data=body, content_type=content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"status": "ok"}


@app.get("/v1/object/proxy")
def proxy_get(token: str = Query(min_length=10)) -> Response:
    try:
        data = app.state.storage_app.proxy_download(token=token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return Response(content=data, media_type="application/octet-stream")


@app.post("/v1/object/head", response_model=HeadResponse, dependencies=[Depends(_authorize)])
def head_object(req: HeadRequest) -> HeadResponse:
    result = app.state.storage_app.head_object(req.object_uri)
    return HeadResponse(exists=result.exists, size=(result.stat.size if result.stat else None))


app.include_router(build_explorer_router(app))
