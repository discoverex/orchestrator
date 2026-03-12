from __future__ import annotations

import json
from pathlib import Path


def read_steps(steps_file: Path) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    if not steps_file.exists():
        return steps
    for raw in steps_file.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        name, status, message = raw.split("\t", 2)
        steps.append({"name": name, "status": status, "message": message})
    return steps


def write_summary_local(
    steps_file: str, summary_file: str, mode: str, flow_run_id: str, mlflow_run_id: str
) -> int:
    steps = read_steps(Path(steps_file))
    summary = {
        "mode": mode,
        "ok": all(step["status"] == "pass" for step in steps),
        "flow_run_id": flow_run_id or None,
        "mlflow_run_id": mlflow_run_id or None,
        "steps": steps,
    }
    target = Path(summary_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return 0


def write_summary_remote(
    steps_file: str,
    summary_file: str,
    flow_run_id: str,
    prefect_api_url: str,
    work_pool: str,
    work_queue: str,
    prune_mode: str,
) -> int:
    steps = read_steps(Path(steps_file))
    summary = {
        "ok": all(step["status"] == "pass" for step in steps),
        "flow_run_id": flow_run_id or None,
        "prefect_api_url": prefect_api_url,
        "work_pool": work_pool,
        "work_queue": work_queue,
        "prune_mode": prune_mode,
        "steps": steps,
    }
    target = Path(summary_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return 0
