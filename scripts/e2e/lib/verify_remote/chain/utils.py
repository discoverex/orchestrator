from __future__ import annotations

import json
from typing import Any, cast
from urllib import error, request

from .errors import VerifyError


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any] | list[dict[str, Any]]:
    body = None
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "orchestrator-e2e/1.0",
    }
    if headers:
        req_headers.update(headers)
    if payload is not None:
        req_headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(url, method=method, data=body, headers=req_headers)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VerifyError(
            "http", f"HTTP_{exc.code}", f"{method} {url} failed: {detail}"
        ) from exc
    except error.URLError as exc:
        raise VerifyError(
            "http", "HTTP_UNREACHABLE", f"{method} {url} unreachable: {exc.reason}"
        ) from exc
    if not raw:
        return {}
    parsed = json.loads(raw.decode("utf-8"))
    if isinstance(parsed, dict):
        return cast(dict[str, Any], parsed)
    if isinstance(parsed, list):
        rows = [row for row in parsed if isinstance(row, dict)]
        return cast(list[dict[str, Any]], rows)
    raise VerifyError(
        "http", "HTTP_BAD_JSON", f"{method} {url} returned non-object JSON"
    )


def gateway_headers(token: str) -> dict[str, str]:
    return {"Content-Type": "application/json"}


def artifact_api_base(storage_api_url: str) -> str:
    base = storage_api_url.rstrip("/")
    if base.endswith("/artifact"):
        return base
    return f"{base}/artifact"
