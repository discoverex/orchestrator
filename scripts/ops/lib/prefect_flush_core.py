from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request

from pydantic import BaseModel, ConfigDict, Field


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise SystemExit(f"missing required env: {name}")
    return value or ""


def iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def json_request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    body = None
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "orchestrator-e2e/1.0",
    }
    if headers:
        req_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = request.Request(url, method=method, data=body, headers=req_headers)
    try:
        with request.urlopen(req, timeout=30) as resp:  # nosec B310 - env-controlled endpoints
            raw = resp.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code} {detail}") from exc
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


class Cursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_end_time: str = ""
    ids_at_last_end_time: list[str] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Cursor":
        if not path.exists():
            return cls(last_end_time="", ids_at_last_end_time=[])
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            last_end_time=str(data.get("last_end_time", "")),
            ids_at_last_end_time=list(data.get("ids_at_last_end_time", [])),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "last_end_time": self.last_end_time,
                    "ids_at_last_end_time": self.ids_at_last_end_time,
                    "updated_at": iso_now(),
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(path)

    def seen(self, run_id: str, end_time: str) -> bool:
        if not self.last_end_time:
            return False
        if end_time < self.last_end_time:
            return True
        if end_time == self.last_end_time and run_id in self.ids_at_last_end_time:
            return True
        return False

    def advance(self, run_id: str, end_time: str) -> None:
        if not self.last_end_time or end_time > self.last_end_time:
            self.last_end_time = end_time
            self.ids_at_last_end_time = [run_id]
            return
        if end_time == self.last_end_time:
            if run_id not in self.ids_at_last_end_time:
                self.ids_at_last_end_time.append(run_id)


def prefect_api_url() -> str:
    return env("PREFECT_API_URL", "http://127.0.0.1:4200/api").rstrip("/")


def prefect_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    cf_id = env("PREFECT_CF_ACCESS_CLIENT_ID", "")
    cf_secret = env("PREFECT_CF_ACCESS_CLIENT_SECRET", "")
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def prefect_post(path: str, payload: dict[str, Any]) -> Any:
    return json_request("POST", f"{prefect_api_url()}/{path.lstrip('/')}" , payload=payload, headers=prefect_headers())


def prefect_get(path: str) -> Any:
    return json_request("GET", f"{prefect_api_url()}/{path.lstrip('/')}" , headers=prefect_headers())


def gateway_headers() -> dict[str, str]:
    headers = {"Authorization": f"Bearer {env('FLUSH_GATEWAY_TOKEN', required=True)}"}
    cf_id = env("FLUSH_CF_ACCESS_CLIENT_ID", "")
    cf_secret = env("FLUSH_CF_ACCESS_CLIENT_SECRET", "")
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def gateway_post(path: str, payload: dict[str, Any]) -> Any:
    base = env("FLUSH_TARGET_URL", required=True).rstrip("/")
    return json_request("POST", f"{base}/{path.lstrip('/')}" , payload=payload, headers=gateway_headers())


def put_presigned(url: str, body: bytes) -> None:
    req = request.Request(
        url,
        method="PUT",
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "orchestrator-e2e/1.0",
        },
    )
    with request.urlopen(req, timeout=60):  # nosec B310 - presigned URL
        return


def fetch_paginated(path: str, *, sort: str, filter_key: str, filter_payload: dict[str, Any], page_size: int = 200) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        rows = prefect_post(
            path,
            {
                "sort": sort,
                "limit": page_size,
                "offset": offset,
                filter_key: filter_payload,
            },
        )
        if not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return out
