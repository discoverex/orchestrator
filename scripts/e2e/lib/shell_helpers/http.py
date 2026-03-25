from __future__ import annotations

import json
from typing import cast
from urllib import parse, request
from urllib.parse import urlsplit, urlunsplit


def http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict[str, object]:
    data = None
    req_headers = {"Accept": "application/json", "User-Agent": "orchestrator-e2e/1.0"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = request.Request(url, method=method, data=data, headers=req_headers)
    with request.urlopen(req, timeout=timeout) as resp:
        parsed = json.loads(resp.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise SystemExit(f"expected JSON object from {method} {url}")
    return cast(dict[str, object], parsed)


def http_text(
    url: str, *, headers: dict[str, str] | None = None, timeout: int = 15
) -> str:
    req_headers = {"Accept": "application/json", "User-Agent": "orchestrator-e2e/1.0"}
    if headers:
        req_headers.update(headers)
    req = request.Request(url, method="GET", headers=req_headers)
    with request.urlopen(req, timeout=timeout) as resp:
        body = cast(bytes, resp.read())
    return body.decode("utf-8")


def artifact_api_base(storage_api_url: str) -> str:
    base = storage_api_url.rstrip("/")
    return base if base.endswith("/artifact") else f"{base}/artifact"


def download_headers(presigned_host_header: str) -> dict[str, str]:
    return {"Host": presigned_host_header} if presigned_host_header else {}


def rewrite_presigned_url(url: str, internal_base_url: str) -> str:
    if not internal_base_url:
        return url
    src = urlsplit(url)
    dst = urlsplit(internal_base_url)
    if not src.scheme or not src.netloc or not dst.scheme or not dst.netloc:
        return url
    host = (src.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost"}:
        return url
    return urlunsplit((dst.scheme, dst.netloc, src.path, src.query, src.fragment))


def extract_json_object(raw: str) -> dict[str, object]:
    for line in reversed(raw.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return cast(dict[str, object], parsed)
    raise SystemExit("unable to extract JSON object from stdout")


def encode_query(query: dict[str, str]) -> str:
    return parse.urlencode(query)
