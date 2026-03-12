from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from scripts.observability.lib.prefect_observe_client import (
    ObserveError,
    PrefectObserveClient,
)


def load_job_spec(path: str) -> str:
    raw = Path(path).read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ObserveError("job spec file must contain a JSON object")
    return json.dumps(parsed, ensure_ascii=True)


def summarize_deployment(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "work_pool_name": row.get("work_pool_name"),
        "work_queue_name": row.get("work_queue_name"),
        "created": row.get("created"),
        "updated": row.get("updated"),
    }


def summarize_flow_run(row: dict[str, Any]) -> dict[str, Any]:
    state = row.get("state")
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "deployment_id": row.get("deployment_id"),
        "work_queue_name": row.get("work_queue_name"),
        "state_type": row.get("state_type") or (state or {}).get("type"),
        "state_name": row.get("state_name") or (state or {}).get("name"),
        "state_message": (state or {}).get("message")
        if isinstance(state, dict)
        else None,
        "created": row.get("created"),
        "expected_start_time": row.get("expected_start_time"),
        "start_time": row.get("start_time"),
        "end_time": row.get("end_time"),
        "infrastructure_pid": row.get("infrastructure_pid"),
    }


def poll_flow_run(
    client: PrefectObserveClient,
    flow_run_id: str,
    *,
    timeout_sec: int = 180,
    poll_interval_sec: int = 5,
) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last: dict[str, Any] | None = None
    while time.time() < deadline:
        current = client.get_flow_run(flow_run_id)
        last = current
        state_type = str(
            current.get("state_type") or current.get("state", {}).get("type") or ""
        ).upper()
        if state_type in {"COMPLETED", "FAILED", "CRASHED", "CANCELLED"}:
            return current
        time.sleep(poll_interval_sec)
    if last is None:
        raise ObserveError("flow run polling produced no response")
    raise ObserveError(
        f"timed out waiting for terminal state: {summarize_flow_run(last)}"
    )


def print_json(payload: dict[str, Any] | list[dict[str, Any]] | bool) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2))
