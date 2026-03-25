from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Header, HTTPException, Request

from storage.application.service import PresignEntry, StorageApplicationService
from storage.interfaces.http_models import (
    DEFAULT_FILENAMES,
    BatchPresignRequest,
    HeadRequest,
    HeadResponse,
    PresignRequest,
    PresignResponse,
)

StorageAuthorizer = Callable[[Request, str | None, str | None], None]


def build_artifact_router(
    storage_app: StorageApplicationService,
    authorize_request: StorageAuthorizer,
    *,
    prefix: str = "/artifact",
) -> APIRouter:
    router = APIRouter(prefix=prefix)

    def filename_for(req: PresignRequest) -> str:
        return req.filename or DEFAULT_FILENAMES[req.kind]

    def to_response(req: PresignRequest, method: str) -> PresignResponse:
        try:
            issued = storage_app.issue_presign(
                flow_run_id=req.flow_run_id,
                attempt=req.attempt,
                filename=filename_for(req),
                method=method,
                ttl_seconds=req.ttl_seconds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return PresignResponse(
            kind=req.kind,
            object_uri=issued.object_uri,
            url=issued.url,
            expires_at=issued.expires_at,
        )

    @router.post("/v1/presign/put", response_model=PresignResponse)
    def presign_put(
        req: PresignRequest,
        request: Request,
        cf_access_client_id: str | None = Header(default=None),
        cf_access_client_secret: str | None = Header(default=None),
    ) -> PresignResponse:
        authorize_request(request, cf_access_client_id, cf_access_client_secret)
        return to_response(req, method="PUT")

    @router.post("/v1/presign/get", response_model=PresignResponse)
    def presign_get(
        req: PresignRequest,
        request: Request,
        cf_access_client_id: str | None = Header(default=None),
        cf_access_client_secret: str | None = Header(default=None),
    ) -> PresignResponse:
        authorize_request(request, cf_access_client_id, cf_access_client_secret)
        return to_response(req, method="GET")

    @router.post("/v1/presign/batch", response_model=list[PresignResponse])
    def presign_batch(
        req: BatchPresignRequest,
        request: Request,
        cf_access_client_id: str | None = Header(default=None),
        cf_access_client_secret: str | None = Header(default=None),
    ) -> list[PresignResponse]:
        authorize_request(request, cf_access_client_id, cf_access_client_secret)
        entries = [
            PresignEntry(
                flow_run_id=req.flow_run_id,
                attempt=req.attempt,
                kind=e.kind.value,
                filename=filename_for(e),
                ttl_seconds=e.ttl_seconds,
            )
            for e in req.entries
        ]
        try:
            rows = storage_app.issue_batch_put(entries=entries)
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

    @router.post("/v1/object/head", response_model=HeadResponse)
    def head_object(
        req: HeadRequest,
        request: Request,
        cf_access_client_id: str | None = Header(default=None),
        cf_access_client_secret: str | None = Header(default=None),
    ) -> HeadResponse:
        authorize_request(request, cf_access_client_id, cf_access_client_secret)
        result = storage_app.head_object(req.object_uri)
        return HeadResponse(
            exists=result.exists, size=(result.stat.size if result.stat else None)
        )

    return router
