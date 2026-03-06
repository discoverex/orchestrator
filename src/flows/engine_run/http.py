from __future__ import annotations

import json
import os
from urllib import request

WORKER_HTTP_USER_AGENT = "orchestrator-worker/1.0"


def gateway_headers() -> dict[str, str]:
    token = os.getenv("STORAGE_GATEWAY_TOKEN", "dev-storage-token")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": WORKER_HTTP_USER_AGENT,
    }


def http_json(method: str, url: str, payload: dict[str, object]) -> dict[str, object] | list[dict[str, object]]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method=method, data=body, headers=gateway_headers())
    with request.urlopen(req) as resp:  # nosec B310 - controlled endpoint from env
        return json.loads(resp.read().decode("utf-8"))


def upload_file(put_url: str, payload: bytes) -> None:
    req = request.Request(
        put_url,
        method="PUT",
        data=payload,
        headers={
            "Content-Type": "application/octet-stream",
            "User-Agent": WORKER_HTTP_USER_AGENT,
        },
    )
    with request.urlopen(req):  # nosec B310 - presigned URL
        return
