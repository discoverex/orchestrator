from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from urllib import error, request
from urllib.parse import urlencode

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, Response

logger = logging.getLogger("worker_router")


@dataclass
class UpstreamConfig:
    name: str
    base_url: str
    headers: dict[str, str]


def _optional_cf_headers(prefix: str = "") -> dict[str, str]:
    cf_id = os.getenv(f"{prefix}CF_ACCESS_CLIENT_ID", "").strip()
    cf_secret = os.getenv(f"{prefix}CF_ACCESS_CLIENT_SECRET", "").strip()
    if cf_id and cf_secret:
        return {
            "CF-Access-Client-Id": cf_id,
            "CF-Access-Client-Secret": cf_secret,
        }
    return {}


def _worker_auth_token() -> str:
    return os.getenv("WORKER_ROUTER_TOKEN", "dev-worker-router-token")


def _storage_upstream() -> UpstreamConfig:
    token = os.getenv("ROUTER_STORAGE_GATEWAY_TOKEN", os.getenv("STORAGE_GATEWAY_TOKEN", "dev-storage-token"))
    headers = {
        "Authorization": f"Bearer {token}",
    }
    headers.update(_optional_cf_headers("ROUTER_STORAGE_"))
    return UpstreamConfig(
        name="storage",
        base_url=os.getenv("ROUTER_STORAGE_BASE_URL", "http://storage-gateway:8100"),
        headers=headers,
    )


def _mlflow_upstream() -> UpstreamConfig:
    headers = _optional_cf_headers("ROUTER_MLFLOW_")
    auth = os.getenv("ROUTER_MLFLOW_AUTHORIZATION", "").strip()
    if auth:
        headers["Authorization"] = auth
    return UpstreamConfig(
        name="mlflow",
        base_url=os.getenv("ROUTER_MLFLOW_BASE_URL", "http://mlflow:5000"),
        headers=headers,
    )


def _check_worker_auth(authorization: str | None) -> None:
    expected = f"Bearer {_worker_auth_token()}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


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
        not in {"host", "content-length", "authorization", "cf-access-client-id", "cf-access-client-secret"}
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
                if key.lower() not in {"transfer-encoding", "content-length", "connection"}
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
            headers={"X-Request-Id": request_id, "Content-Type": exc.headers.get("Content-Type", "application/json")},
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
            ).encode("utf-8"),
            status_code=502,
            media_type="application/json",
            headers={"X-Request-Id": request_id},
        )


def create_app() -> FastAPI:
    app = FastAPI(title="orchestrator-worker-router")
    router = APIRouter()
    storage = _storage_upstream()
    mlflow = _mlflow_upstream()

    @router.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.api_route("/storage/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
    async def storage_proxy(
        path: str,
        request_in: Request,
        authorization: str | None = Header(default=None),
    ) -> Response:
        _check_worker_auth(authorization)
        return await _proxy(request_in, storage, path)

    @router.api_route("/mlflow/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
    async def mlflow_proxy(
        path: str,
        request_in: Request,
        authorization: str | None = Header(default=None),
    ) -> Response:
        _check_worker_auth(authorization)
        return await _proxy(request_in, mlflow, path)

    app.include_router(router)
    return app
