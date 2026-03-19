from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from urllib import error, request

from fastapi import Request, Response

from common.prefect.client_env import build_prefect_client_headers

logger = logging.getLogger("worker_router")


@dataclass
class UpstreamConfig:
    name: str
    base_url: str
    headers: dict[str, str]


def mlflow_upstream() -> UpstreamConfig:
    headers: dict[str, str] = {}
    auth = os.getenv("MLFLOW_INTERNAL_AUTHORIZATION", "").strip()
    if auth:
        headers["Authorization"] = auth
    return UpstreamConfig(
        name="mlflow",
        base_url=os.getenv("MLFLOW_BACKEND_URL", "http://mlflow:5000").rstrip("/"),
        headers=headers,
    )


def prefect_upstream() -> UpstreamConfig:
    return UpstreamConfig(
        name="prefect",
        base_url=os.getenv("PREFECT_UPSTREAM_URL", "").rstrip("/"),
        headers=build_prefect_client_headers(dict(os.environ)),
    )


def _is_expected_prefect_csrf_probe(
    upstream: UpstreamConfig,
    path: str,
    status_code: int,
    payload: bytes,
) -> bool:
    if upstream.name != "prefect" or status_code != 422:
        return False
    normalized_path = path.lstrip("/")
    if normalized_path != "api/csrf-token":
        return False
    return b"CSRF protection is disabled." in payload


async def proxy_request(
    request_in: Request,
    upstream: UpstreamConfig,
    path: str,
) -> Response:
    request_id = request_in.headers.get("X-Request-Id", str(uuid.uuid4()))
    body = await request_in.body()
    target = f"{upstream.base_url.rstrip('/')}/{path.lstrip('/')}"
    if request_in.url.query:
        target = f"{target}?{request_in.url.query}"

    headers = {
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
    headers.update(upstream.headers)
    headers["X-Request-Id"] = request_id
    req = request.Request(
        target,
        method=request_in.method,
        data=body or None,
        headers=headers,
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            payload = resp.read()
            forwarded = {
                key: value
                for key, value in resp.headers.items()
                if key.lower()
                not in {"transfer-encoding", "content-length", "connection"}
            }
            forwarded["X-Request-Id"] = request_id
            logger.info(
                "proxy_ok upstream=%s method=%s path=%s status=%s request_id=%s",
                upstream.name,
                request_in.method,
                request_in.url.path,
                resp.status,
                request_id,
            )
            return Response(content=payload, status_code=resp.status, headers=forwarded)
    except error.HTTPError as exc:
        payload = exc.read()
        preview = payload.decode("utf-8", errors="replace")[:200].replace("\n", "\\n")
        if _is_expected_prefect_csrf_probe(upstream, path, exc.code, payload):
            logger.info(
                "proxy_expected_http upstream=%s method=%s path=%s "
                "status=%s request_id=%s",
                upstream.name,
                request_in.method,
                request_in.url.path,
                exc.code,
                request_id,
            )
        else:
            logger.warning(
                "proxy_http_error "
                "upstream=%s method=%s path=%s status=%s request_id=%s preview=%s",
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
                f'{{"upstream":"{upstream.name}",'
                f'"detail":"{str(exc.reason)}","request_id":"{request_id}"}}'
            ).encode(),
            status_code=502,
            media_type="application/json",
            headers={"X-Request-Id": request_id},
        )
