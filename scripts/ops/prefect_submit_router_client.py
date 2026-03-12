from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def prefect_api_url() -> str:
    return env("PREFECT_API_URL", "http://127.0.0.1:4200/api").rstrip("/")


def headers() -> dict[str, str]:
    out: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "orchestrator-router/1.0",
    }
    cf_id = env("CF_ACCESS_CLIENT_ID")
    cf_secret = env("CF_ACCESS_CLIENT_SECRET")
    if cf_id and cf_secret:
        out["CF-Access-Client-Id"] = cf_id
        out["CF-Access-Client-Secret"] = cf_secret
    return out


def http_json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    url = f"{prefect_api_url()}/{path.lstrip('/')}"
    body = None
    req_headers = headers()
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = request.Request(url, method=method, data=body, headers=req_headers)
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def count_for_queue(
    queue_name: str, state_types: list[str], max_rows: int = 200
) -> int:
    rows = http_json(
        "POST",
        "flow_runs/filter",
        {
            "sort": "EXPECTED_START_TIME_ASC",
            "limit": max_rows,
            "offset": 0,
            "flow_runs": {
                "state": {"type": {"any_": state_types}},
                "work_queue_name": {"any_": [queue_name]},
            },
        },
    )
    return len(rows) if isinstance(rows, list) else 0


def scheduled_count_for_queue(queue_name: str, max_rows: int = 200) -> int:
    return count_for_queue(queue_name, ["SCHEDULED", "PENDING"], max_rows=max_rows)


def running_count_for_queue(queue_name: str, max_rows: int = 200) -> int:
    return count_for_queue(queue_name, ["RUNNING"], max_rows=max_rows)


def find_deployment_id(deployment_name: str) -> str:
    rows = http_json(
        "POST",
        "deployments/filter",
        {
            "sort": "NAME_ASC",
            "limit": 20,
            "offset": 0,
            "deployments": {"name": {"any_": [deployment_name]}},
        },
    )
    if not isinstance(rows, list):
        raise RuntimeError("unexpected deployments/filter response shape")
    for row in rows:
        if str(row.get("name", "")) == deployment_name:
            dep_id = str(row.get("id", ""))
            if dep_id:
                return dep_id
    raise RuntimeError(f"deployment not found: {deployment_name}")


def create_flow_run(
    deployment_id: str, parameters: dict[str, Any], flow_run_name: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"parameters": parameters}
    if flow_run_name:
        payload["name"] = flow_run_name
    row = http_json("POST", f"deployments/{deployment_id}/create_flow_run", payload)
    if not isinstance(row, dict):
        raise RuntimeError("unexpected create_flow_run response shape")
    return row
