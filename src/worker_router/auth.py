from __future__ import annotations

import os

from fastapi import Request

from common.cloudflare.access import normalize_host, require_service_token


def router_is_local_only() -> bool:
    return os.getenv("WORKER_ROUTER_LOCAL_ONLY", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def check_gateway_auth(
    cf_access_client_id: str | None,
    cf_access_client_secret: str | None,
) -> None:
    require_service_token(
        enabled=os.getenv("GATEWAY_REQUIRE_CF_ACCESS", "true").lower()
        in {"1", "true", "yes", "on"},
        expected_id=os.getenv("CF_ACCESS_CLIENT_ID", "").strip(),
        expected_secret=os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip(),
        provided_id=cf_access_client_id,
        provided_secret=cf_access_client_secret,
    )


def storage_host_mode(request_in: Request) -> str:
    host = normalize_host(request_in.headers.get("host"))
    storage_api_host = normalize_host(os.getenv("STORAGE_API_HOST", ""))
    storage_human_host = normalize_host(os.getenv("STORAGE_HUMAN_HOST", ""))
    if storage_api_host and host == storage_api_host:
        return "machine"
    if storage_human_host and host == storage_human_host:
        return "human"
    return "compat"


def authorize_storage_request(
    request_in: Request,
    cf_access_client_id: str | None,
    cf_access_client_secret: str | None,
) -> None:
    if router_is_local_only():
        return
    if storage_host_mode(request_in) == "human":
        return
    check_gateway_auth(cf_access_client_id, cf_access_client_secret)
