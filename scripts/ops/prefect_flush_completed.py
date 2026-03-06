#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.ops.lib import prefect_flush_core as core  # noqa: E402

Cursor = core.Cursor


def _env(name: str, default: str | None = None, *, required: bool = False) -> str:
    return core.env(name, default, required=required)


def _iso_now() -> str:
    return core.iso_now()


def _prefect_post(path: str, payload: dict[str, Any]) -> Any:
    return core.prefect_post(path, payload)


def _prefect_get(path: str) -> Any:
    return core.prefect_get(path)


def _gateway_post(path: str, payload: dict[str, Any]) -> Any:
    return core.gateway_post(path, payload)


def _put_presigned(url: str, body: bytes) -> None:
    core.put_presigned(url, body)


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
    task_runs = core.fetch_paginated(
        "task_runs/filter",
        sort="EXPECTED_START_TIME_ASC",
        filter_key="task_runs",
        filter_payload={"flow_run_id": {"any_": [run_id]}},
    )
    logs = core.fetch_paginated(
        "logs/filter",
        sort="TIMESTAMP_ASC",
        filter_key="logs",
        filter_payload={"flow_run_id": {"any_": [run_id]}},
    )
    return {
        "schema_version": 1,
        "exported_at": _iso_now(),
        "source": {"prefect_api_url": core.prefect_api_url(), "flow_run_id": run_id},
        "flow_run": flow_run,
        "task_runs": task_runs,
        "logs": logs,
    }


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
