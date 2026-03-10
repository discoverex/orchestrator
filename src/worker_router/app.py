from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from urllib import error, request

from fastapi import APIRouter, FastAPI, Header, Request, Response

from common.cloudflare_access import normalize_host, require_service_token
from storage.composition.container import build_storage_app_from_env
from storage.interfaces import build_artifact_router

logger = logging.getLogger("worker_router")


@dataclass
class UpstreamConfig:
    name: str
    base_url: str
    headers: dict[str, str]


def _mlflow_upstream() -> UpstreamConfig:
    headers: dict[str, str] = {}
    auth = os.getenv("MLFLOW_INTERNAL_AUTHORIZATION", "").strip()
    if auth:
        headers["Authorization"] = auth
    return UpstreamConfig(
        name="mlflow",
        base_url=os.getenv("MLFLOW_BACKEND_URL", "http://mlflow:5000"),
        headers=headers,
    )


def _check_gateway_auth(
    cf_access_client_id: str | None, cf_access_client_secret: str | None
) -> None:
    require_service_token(
        enabled=os.getenv("GATEWAY_REQUIRE_CF_ACCESS", "true").lower()
        in {
            "1",
            "true",
            "yes",
            "on",
        },
        expected_id=os.getenv("CF_ACCESS_CLIENT_ID", "").strip(),
        expected_secret=os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip(),
        provided_id=cf_access_client_id,
        provided_secret=cf_access_client_secret,
    )


def _storage_host_mode(request_in: Request) -> str:
    host = normalize_host(request_in.headers.get("host"))
    storage_api_host = normalize_host(os.getenv("STORAGE_API_HOST", ""))
    storage_human_host = normalize_host(os.getenv("STORAGE_HUMAN_HOST", ""))
    if storage_api_host and host == storage_api_host:
        return "machine"
    if storage_human_host and host == storage_human_host:
        return "human"
    return "compat"


def _authorize_storage_request(
    request_in: Request,
    cf_access_client_id: str | None,
    cf_access_client_secret: str | None,
) -> None:
    mode = _storage_host_mode(request_in)
    if mode == "human":
        return
    _check_gateway_auth(cf_access_client_id, cf_access_client_secret)


async def _proxy(request_in: Request, upstream: UpstreamConfig, path: str) -> Response:
    request_id = request_in.headers.get("X-Request-Id", str(uuid.uuid4()))
    body = await request_in.body()
    query = request_in.url.query
    target = f"{upstream.base_url.rstrip('/')}/{path.lstrip('/')}"
    if query:
        target = f"{target}?{query}"

    forward_headers = {
        key: value
        for key, value in request_in.headers.items()
        if key.lower()
        not in {
            "host",
            "content-length",
            "authorization",
            "cf-access-client-id",
            "cf-access-client-secret",
        }
    }
    forward_headers.update(upstream.headers)
    forward_headers["X-Request-Id"] = request_id
    req = request.Request(
        target,
        method=request_in.method,
        data=body or None,
        headers=forward_headers,
    )
    try:
        with request.urlopen(req, timeout=60) as resp:  # nosec B310
            payload = resp.read()
            headers = {
                key: value
                for key, value in resp.headers.items()
                if key.lower()
                not in {"transfer-encoding", "content-length", "connection"}
            }
            headers["X-Request-Id"] = request_id
            logger.info(
                "proxy_ok upstream=%s method=%s path=%s status=%s request_id=%s",
                upstream.name,
                request_in.method,
                request_in.url.path,
                resp.status,
                request_id,
            )
            return Response(content=payload, status_code=resp.status, headers=headers)
    except error.HTTPError as exc:
        payload = exc.read()
        preview = payload.decode("utf-8", errors="replace")[:200].replace("\n", "\\n")
        logger.warning(
            "proxy_http_error upstream=%s method=%s path=%s status=%s request_id=%s preview=%s",
            upstream.name,
            request_in.method,
            request_in.url.path,
            exc.code,
            request_id,
            preview,
        )
        return Response(
            content=payload,
            status_code=exc.code,
            headers={
                "X-Request-Id": request_id,
                "Content-Type": exc.headers.get("Content-Type", "application/json"),
            },
        )
    except error.URLError as exc:
        logger.error(
            "proxy_network_error upstream=%s method=%s path=%s request_id=%s reason=%s",
            upstream.name,
            request_in.method,
            request_in.url.path,
            request_id,
            exc.reason,
        )
        return Response(
            content=(
                f'{{"upstream":"{upstream.name}","detail":"{str(exc.reason)}","request_id":"{request_id}"}}'
            ).encode(),
            status_code=502,
            media_type="application/json",
            headers={"X-Request-Id": request_id},
        )


def create_app() -> FastAPI:
    app = FastAPI(title="orchestrator-worker-router")
    router = APIRouter()
    mlflow = _mlflow_upstream()
    storage_app = build_storage_app_from_env()
    app.state.storage_app = storage_app

    @router.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.api_route(
        "/mlflow/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
    )
    async def mlflow_proxy(
        path: str,
        request_in: Request,
        cf_access_client_id: str | None = Header(default=None),
        cf_access_client_secret: str | None = Header(default=None),
    ) -> Response:
        _check_gateway_auth(cf_access_client_id, cf_access_client_secret)
        return await _proxy(request_in, mlflow, path)

    app.include_router(router)
    app.include_router(
        build_artifact_router(
            storage_app,
            _authorize_storage_request,
            prefix="/artifact",
        )
    )
    # Compatibility path for existing WORKER_ROUTER_URL clients.
    app.include_router(
        build_artifact_router(
            storage_app,
            _authorize_storage_request,
            prefix="/storage/artifact",
        )
    )
    return app
