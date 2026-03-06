#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request


def _env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise SystemExit(f"missing required env: {name}")
    return value or ""


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_iso8601(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(UTC)


def _json_request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    body = None
    req_headers = {"Accept": "application/json"}
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


@dataclass
class Cursor:
    last_end_time: str = ""
    ids_at_last_end_time: list[str] | None = None

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
                    "ids_at_last_end_time": self.ids_at_last_end_time or [],
                    "updated_at": _iso_now(),
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
        if end_time == self.last_end_time and run_id in (self.ids_at_last_end_time or []):
            return True
        return False

    def advance(self, run_id: str, end_time: str) -> None:
        if not self.last_end_time or end_time > self.last_end_time:
            self.last_end_time = end_time
            self.ids_at_last_end_time = [run_id]
            return
        if end_time == self.last_end_time:
            ids = self.ids_at_last_end_time or []
            if run_id not in ids:
                ids.append(run_id)
            self.ids_at_last_end_time = ids


def _prefect_api_url() -> str:
    return _env("PREFECT_API_URL", "http://127.0.0.1:4200/api").rstrip("/")


def _prefect_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    cf_id = _env("PREFECT_CF_ACCESS_CLIENT_ID", "")
    cf_secret = _env("PREFECT_CF_ACCESS_CLIENT_SECRET", "")
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _prefect_post(path: str, payload: dict[str, Any]) -> Any:
    return _json_request("POST", f"{_prefect_api_url()}/{path.lstrip('/')}", payload=payload, headers=_prefect_headers())


def _prefect_get(path: str) -> Any:
    return _json_request("GET", f"{_prefect_api_url()}/{path.lstrip('/')}", headers=_prefect_headers())


def _gateway_headers() -> dict[str, str]:
    headers = {"Authorization": f"Bearer {_env('FLUSH_GATEWAY_TOKEN', required=True)}"}
    cf_id = _env("FLUSH_CF_ACCESS_CLIENT_ID", "")
    cf_secret = _env("FLUSH_CF_ACCESS_CLIENT_SECRET", "")
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _gateway_post(path: str, payload: dict[str, Any]) -> Any:
    base = _env("FLUSH_TARGET_URL", required=True).rstrip("/")
    return _json_request("POST", f"{base}/{path.lstrip('/')}", payload=payload, headers=_gateway_headers())


def _put_presigned(url: str, body: bytes) -> None:
    req = request.Request(url, method="PUT", data=body, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=60):  # nosec B310 - presigned URL
        return


def _list_completed_runs(after_end_time: str, page_size: int, max_runs: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    offset = 0
    while len(output) < max_runs:
        payload: dict[str, Any] = {
            "sort": "END_TIME_DESC",
            "limit": page_size,
            "offset": offset,
            "flow_runs": {"state": {"type": {"any_": ["COMPLETED"]}}},
        }
        if after_end_time:
            payload["flow_runs"]["end_time"] = {"after_": after_end_time}
        rows = _prefect_post("flow_runs/filter", payload)
        if not rows:
            break
        if not isinstance(rows, list):
            raise RuntimeError("unexpected flow_runs/filter response")
        output.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return output[:max_runs]


def _fetch_run_snapshot(run_id: str) -> dict[str, Any]:
    flow_run = _prefect_get(f"flow_runs/{run_id}")
    task_runs = _fetch_paginated(
        "task_runs/filter",
        sort="EXPECTED_START_TIME_ASC",
        filter_key="task_runs",
        filter_payload={"flow_run_id": {"any_": [run_id]}},
    )
    logs = _fetch_paginated(
        "logs/filter",
        sort="TIMESTAMP_ASC",
        filter_key="logs",
        filter_payload={"flow_run_id": {"any_": [run_id]}},
    )
    return {
        "schema_version": 1,
        "exported_at": _iso_now(),
        "source": {"prefect_api_url": _prefect_api_url(), "flow_run_id": run_id},
        "flow_run": flow_run,
        "task_runs": task_runs if isinstance(task_runs, list) else [],
        "logs": logs if isinstance(logs, list) else [],
    }


def _fetch_paginated(path: str, *, sort: str, filter_key: str, filter_payload: dict[str, Any], page_size: int = 200) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        rows = _prefect_post(
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


def _upload_snapshot(flow_run: dict[str, Any], snapshot: dict[str, Any]) -> str:
    run_id = str(flow_run.get("id"))
    attempt = int(flow_run.get("run_count") or 1)
    filename = f"prefect-run-{run_id}.json"
    presign = _gateway_post(
        "v1/presign/put",
        {
            "flow_run_id": run_id,
            "attempt": attempt,
            "kind": "custom",
            "filename": filename,
        },
    )
    put_url = str(presign["url"])
    object_uri = str(presign["object_uri"])
    _put_presigned(put_url, json.dumps(snapshot, ensure_ascii=True, indent=2).encode("utf-8"))
    return object_uri


def main() -> int:
    parser = argparse.ArgumentParser(description="Flush completed Prefect runs to storage-gateway as full JSON snapshots.")
    parser.add_argument("--once", action="store_true", help="run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="collect snapshots without upload or cursor update")
    parser.add_argument("--cursor-path", default=_env("FLUSH_CURSOR_PATH", "/var/lib/orchestrator/prefect-flush/cursor.json"))
    parser.add_argument("--page-size", type=int, default=int(_env("FLUSH_PAGE_SIZE", "100")))
    parser.add_argument("--max-runs", type=int, default=int(_env("FLUSH_MAX_RUNS", "500")))
    args = parser.parse_args()

    cursor_path = Path(args.cursor_path)
    cursor = Cursor.load(cursor_path)
    runs = _list_completed_runs(cursor.last_end_time, page_size=args.page_size, max_runs=args.max_runs)

    exported = 0
    skipped = 0
    uploaded: list[dict[str, str]] = []
    for run in runs:
        run_id = str(run.get("id", ""))
        end_time = str(run.get("end_time") or "")
        if not run_id or not end_time:
            skipped += 1
            continue
        if cursor.seen(run_id, end_time):
            skipped += 1
            continue
        snapshot = _fetch_run_snapshot(run_id)
        if not args.dry_run:
            object_uri = _upload_snapshot(run, snapshot)
            uploaded.append({"flow_run_id": run_id, "object_uri": object_uri})
            cursor.advance(run_id, end_time)
            cursor.save(cursor_path)
        exported += 1

    summary = {
        "timestamp": _iso_now(),
        "runs_seen": len(runs),
        "runs_exported": exported,
        "runs_skipped": skipped,
        "dry_run": args.dry_run,
        "cursor_path": str(cursor_path),
        "uploaded": uploaded,
    }
    print(json.dumps(summary, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
