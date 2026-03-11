from __future__ import annotations

import json
import os
from typing import cast
from urllib import request

WORKER_HTTP_USER_AGENT = "orchestrator-worker/1.0"


def storage_base_url() -> str:
    storage_api_url = os.getenv("STORAGE_API_URL", "").strip().rstrip("/")
    if storage_api_url:
        return f"{storage_api_url}/artifact"
    raise RuntimeError("missing required environment variable: STORAGE_API_URL")


def gateway_headers() -> dict[str, str]:
    cf_id = os.getenv("CF_ACCESS_CLIENT_ID", "").strip()
    cf_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip()
    if not os.getenv("STORAGE_API_URL", "").strip() or not cf_id or not cf_secret:
        raise RuntimeError(
            "missing required environment variables: STORAGE_API_URL, CF_ACCESS_CLIENT_ID, CF_ACCESS_CLIENT_SECRET"
        )
    return {
        "Content-Type": "application/json",
        "User-Agent": WORKER_HTTP_USER_AGENT,
        "CF-Access-Client-Id": cf_id,
        "CF-Access-Client-Secret": cf_secret,
    }


def http_json(
    method: str, url: str, payload: dict[str, object]
) -> dict[str, object] | list[dict[str, object]]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method=method, data=body, headers=gateway_headers())
    with request.urlopen(req) as resp:  # nosec B310 - controlled endpoint from env
        text = resp.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        preview = text[:200].replace("\n", "\\n")
        raise RuntimeError(
            f"non-json response from storage API: {preview}"
        ) from exc
    if isinstance(parsed, dict):
        return cast(dict[str, object], parsed)
    if isinstance(parsed, list):
        rows = [row for row in parsed if isinstance(row, dict)]
        return cast(list[dict[str, object]], rows)
    raise RuntimeError("unexpected json response type")


def upload_file(put_url: str, payload: bytes) -> None:
    headers = {
        "Content-Type": "application/octet-stream",
        "User-Agent": WORKER_HTTP_USER_AGENT,
    }
    cf_id = os.getenv("CF_ACCESS_CLIENT_ID", "").strip()
    cf_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    req = request.Request(
        put_url,
        method="PUT",
        data=payload,
        headers=headers,
    )
    with request.urlopen(req):  # nosec B310 - presigned URL
        return
