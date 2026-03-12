#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from flows.job_spec import parse_job_spec_json
from scripts.ops.prefect_submit_router_client import (
    create_flow_run,
    env,
    find_deployment_id,
    running_count_for_queue,
    scheduled_count_for_queue,
)
from scripts.ops.prefect_submit_router_policy import (
    QueueDepth,
    select_deployment,
)

DEFAULT_FIXED_DEPLOYMENT = "e2e-job/e2e-test"
DEFAULT_COLAB_DEPLOYMENT = "e2e-job/e2e-test-colab"


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit flow run "
        "to fixed/colab deployment based on queue-depth policy."
    )
    parser.add_argument(
        "--mode",
        default=env("WORKER_ROUTING_MODE", "fixed-first"),
        choices=("fixed-first", "colab-first"),
    )
    parser.add_argument(
        "--strict-priority", default=env("WORKER_ROUTING_STRICT_PRIORITY", "false")
    )
    parser.add_argument(
        "--queue-depth-threshold",
        type=int,
        default=int(env("WORKER_ROUTING_QUEUE_DEPTH_THRESHOLD", "1")),
    )
    parser.add_argument(
        "--divert-when-running",
        default=env("WORKER_ROUTING_DIVERT_WHEN_RUNNING", "true"),
    )
    parser.add_argument(
        "--fixed-deployment",
        default=env("ROUTER_FIXED_DEPLOYMENT", DEFAULT_FIXED_DEPLOYMENT),
    )
    parser.add_argument(
        "--colab-deployment",
        default=env("ROUTER_COLAB_DEPLOYMENT", DEFAULT_COLAB_DEPLOYMENT),
    )
    parser.add_argument("--fixed-queue", default=env("ROUTER_FIXED_QUEUE", "gpu-fixed"))
    parser.add_argument("--colab-queue", default=env("ROUTER_COLAB_QUEUE", "gpu-colab"))
    parser.add_argument("--job-spec-json", default=None)
    parser.add_argument("--job-spec-file", default=None)
    parser.add_argument("--resume-key", default=None)
    parser.add_argument("--checkpoint-dir", default=None)
    parser.add_argument("--parameters-json", default=None)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    fixed_depth = QueueDepth(
        args.fixed_queue,
        scheduled_count_for_queue(args.fixed_queue),
        running_count_for_queue(args.fixed_queue),
    )
    colab_depth = QueueDepth(
        args.colab_queue,
        scheduled_count_for_queue(args.colab_queue),
        running_count_for_queue(args.colab_queue),
    )

    decision = select_deployment(
        mode=args.mode,
        strict_priority=_parse_bool(args.strict_priority),
        divert_when_running=_parse_bool(args.divert_when_running),
        queue_depth_threshold=args.queue_depth_threshold,
        fixed_depth=fixed_depth,
        colab_depth=colab_depth,
        fixed_deployment=args.fixed_deployment,
        colab_deployment=args.colab_deployment,
    )
    selected = decision.selected_deployment
    decision_reason = decision.reason

    job_spec_raw = (
        Path(args.job_spec_file).read_text(encoding="utf-8")
        if args.job_spec_file
        else str(args.job_spec_json)
    )
    job_spec = parse_job_spec_json(job_spec_raw).model_dump(mode="json")
    if args.parameters_json:
        job_spec.update(json.loads(args.parameters_json))
        job_spec_raw = json.dumps(job_spec, ensure_ascii=True)

    dep_id = find_deployment_id(selected)
    created = create_flow_run(
        dep_id,
        {
            "job_spec_json": job_spec_raw,
            "resume_key": args.resume_key,
            "checkpoint_dir": args.checkpoint_dir,
        },
        flow_run_name=job_spec.get("job_name"),
    )

    print(
        json.dumps(
            {
                "ok": True,
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "selected_deployment": selected,
                "selected_deployment_id": dep_id,
                "reason": decision_reason,
                "flow_run_id": created.get("id"),
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
