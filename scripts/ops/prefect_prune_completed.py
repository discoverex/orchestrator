#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import request


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _api_url() -> str:
    return _env("PREFECT_API_URL", "http://127.0.0.1:4200/api").rstrip("/")


def _prefect_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    cf_id = os.getenv("CF_ACCESS_CLIENT_ID", "")
    cf_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "")
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _json_request(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    body = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "orchestrator-e2e/1.0",
    }
    headers.update(_prefect_headers())
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        f"{_api_url()}/{path.lstrip('/')}", method=method, data=body, headers=headers
    )
    with request.urlopen(req, timeout=30) as resp:  # nosec B310 - env-controlled endpoint
        raw = resp.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _list_targets(
    cutoff_iso: str, page_size: int, max_runs: int
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    offset = 0
    while len(output) < max_runs:
        payload = {
            "sort": "END_TIME_DESC",
            "limit": page_size,
            "offset": offset,
            "flow_runs": {
                "state": {"type": {"any_": ["COMPLETED"]}},
                "end_time": {"before_": cutoff_iso},
            },
        }
        rows = _json_request("POST", "flow_runs/filter", payload)
        if not rows:
            break
        if not isinstance(rows, list):
            raise RuntimeError("unexpected flow_runs/filter response")
        output.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return output[:max_runs]


def _delete_run(run_id: str) -> None:
    _json_request("DELETE", f"flow_runs/{run_id}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prune completed Prefect runs older than TTL."
    )
    parser.add_argument(
        "--apply", action="store_true", help="actually delete runs; default is dry-run"
    )
    parser.add_argument(
        "--ttl-hours", type=int, default=int(_env("PRUNE_TTL_HOURS", "72"))
    )
    parser.add_argument(
        "--page-size", type=int, default=int(_env("PRUNE_PAGE_SIZE", "200"))
    )
    parser.add_argument(
        "--max-runs", type=int, default=int(_env("PRUNE_MAX_RUNS", "1000"))
    )
    args = parser.parse_args()

    cutoff = datetime.now(UTC) - timedelta(hours=args.ttl_hours)
    cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")
    targets = _list_targets(
        cutoff_iso=cutoff_iso, page_size=args.page_size, max_runs=args.max_runs
    )

    deleted = 0
    for row in targets:
        run_id = str(row.get("id", ""))
        if not run_id:
            continue
        if args.apply:
            _delete_run(run_id)
            deleted += 1

    print(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "cutoff": cutoff_iso,
                "candidates": len(targets),
                "deleted": deleted,
                "dry_run": not args.apply,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
