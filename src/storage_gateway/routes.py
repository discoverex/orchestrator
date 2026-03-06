from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response

from storage.application.service import PresignEntry
from storage_gateway.auth import authorize_dependency
from storage_gateway.models import (
    DEFAULT_FILENAMES,
    BatchPresignRequest,
    HeadRequest,
    HeadResponse,
    PresignRequest,
    PresignResponse,
)


def build_router(app: FastAPI) -> APIRouter:
    router = APIRouter()
    authorize = authorize_dependency(app)

    def filename_for(req: PresignRequest) -> str:
        return req.filename or DEFAULT_FILENAMES[req.kind]

    def to_response(
        req: PresignRequest, method: str, request: Request
    ) -> PresignResponse:
        try:
            issued = app.state.storage_app.issue_presign(
                flow_run_id=req.flow_run_id,
                attempt=req.attempt,
                filename=filename_for(req),
                method=method,
                base_url=str(request.base_url),
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

    @router.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.post(
        "/v1/presign/put",
        response_model=PresignResponse,
        dependencies=[Depends(authorize)],
    )
    def presign_put(req: PresignRequest, request: Request) -> PresignResponse:
        return to_response(req, method="PUT", request=request)

    @router.post(
        "/v1/presign/get",
        response_model=PresignResponse,
        dependencies=[Depends(authorize)],
    )
    def presign_get(req: PresignRequest, request: Request) -> PresignResponse:
        return to_response(req, method="GET", request=request)

    @router.post(
        "/v1/presign/batch",
        response_model=list[PresignResponse],
        dependencies=[Depends(authorize)],
    )
    def presign_batch(
        req: BatchPresignRequest, request: Request
    ) -> list[PresignResponse]:
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
            rows = app.state.storage_app.issue_batch_put(
                entries=entries, base_url=str(request.base_url)
            )
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

    @router.put("/v1/object/proxy")
    async def proxy_put(
        request: Request, token: str = Query(min_length=10)
    ) -> dict[str, str]:
        body = await request.body()
        content_type = request.headers.get("content-type", "application/octet-stream")
        try:
            app.state.storage_app.proxy_upload(
                token=token, data=body, content_type=content_type
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return {"status": "ok"}

    @router.get("/v1/object/proxy")
    def proxy_get(token: str = Query(min_length=10)) -> Response:
        try:
            data = app.state.storage_app.proxy_download(token=token)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return Response(content=data, media_type="application/octet-stream")

    @router.post(
        "/v1/object/head",
        response_model=HeadResponse,
        dependencies=[Depends(authorize)],
    )
    def head_object(req: HeadRequest) -> HeadResponse:
        result = app.state.storage_app.head_object(req.object_uri)
        return HeadResponse(
            exists=result.exists, size=(result.stat.size if result.stat else None)
        )

    return router
