from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..summary import read_steps


def cmd_write_summary_local(args: argparse.Namespace) -> int:
    steps = read_steps(Path(args.steps_file))
    summary = {
        "mode": args.mode,
        "ok": all(step["status"] == "pass" for step in steps),
        "flow_run_id": args.flow_run_id or None,
        "mlflow_run_id": args.mlflow_run_id or None,
        "steps": steps,
    }
    summary_file = Path(args.summary_file)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return 0


def cmd_write_summary_remote(args: argparse.Namespace) -> int:
    steps = read_steps(Path(args.steps_file))
    summary = {
        "ok": all(step["status"] == "pass" for step in steps),
        "flow_run_id": args.flow_run_id or None,
        "prefect_api_url": args.prefect_api_url,
        "work_pool": args.work_pool,
        "work_queue": args.work_queue,
        "prune_mode": args.prune_mode,
        "steps": steps,
    }
    summary_file = Path(args.summary_file)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return 0
