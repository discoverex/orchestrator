#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from common.prefect.deployment_targets import (
    DEFAULT_COLAB_DEPLOYMENT_NAME,
    DEFAULT_FIXED_DEPLOYMENT_NAME,
    DEFAULT_FLOW_NAME,
    default_colab_deployment_fqn,
    default_fixed_deployment_fqn,
    deployment_fqn,
)
from scripts.ops.prefect_submit_router_client import (
    create_flow_run,
    env,
    find_deployment_id,
    running_count_for_queue,
    scheduled_count_for_queue,
)
from scripts.ops.prefect_submit_router_policy import (
    QueueDepth,
    parse_and_merge_parameters,
    select_deployment,
)

DEFAULT_FIXED_DEPLOYMENT = default_fixed_deployment_fqn()
DEFAULT_COLAB_DEPLOYMENT = default_colab_deployment_fqn()


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_deployment_target(
    *,
    explicit_fqn: str | None,
    env_fqn: str | None,
    flow_name_env: str,
    deployment_name_env: str,
    default_flow_name: str,
    default_deployment_name: str,
) -> str:
    if explicit_fqn:
        return explicit_fqn
    if env_fqn:
        return env_fqn
    return deployment_fqn(
        env(flow_name_env, default_flow_name),
        env(deployment_name_env, default_deployment_name),
    )


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
    parser.add_argument("--fixed-deployment", default=None)
    parser.add_argument("--colab-deployment", default=None)
    parser.add_argument("--fixed-queue", default=env("ROUTER_FIXED_QUEUE", "gpu-fixed"))
    parser.add_argument("--colab-queue", default=env("ROUTER_COLAB_QUEUE", "gpu-colab"))
    parser.add_argument("--parameters-json", default=None)
    parser.add_argument("--parameters-file", default=None)
    parser.add_argument("--resume-key", default=None)
    parser.add_argument("--checkpoint-dir", default=None)
    parser.add_argument("--parameter-overrides-json", default=None)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    fixed_deployment = _resolve_deployment_target(
        explicit_fqn=args.fixed_deployment,
        env_fqn=env("ROUTER_FIXED_DEPLOYMENT", ""),
        flow_name_env="ROUTER_FLOW_NAME",
        deployment_name_env="ROUTER_FIXED_DEPLOYMENT_NAME",
        default_flow_name=DEFAULT_FLOW_NAME,
        default_deployment_name=DEFAULT_FIXED_DEPLOYMENT_NAME,
    )
    colab_deployment = _resolve_deployment_target(
        explicit_fqn=args.colab_deployment,
        env_fqn=env("ROUTER_COLAB_DEPLOYMENT", ""),
        flow_name_env="ROUTER_FLOW_NAME",
        deployment_name_env="ROUTER_COLAB_DEPLOYMENT_NAME",
        default_flow_name=DEFAULT_FLOW_NAME,
        default_deployment_name=DEFAULT_COLAB_DEPLOYMENT_NAME,
    )
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
        fixed_deployment=fixed_deployment,
        colab_deployment=colab_deployment,
    )
    selected = decision.selected_deployment
    decision_reason = decision.reason

    parameters_raw = (
        Path(args.parameters_file).read_text(encoding="utf-8")
        if args.parameters_file
        else str(args.parameters_json)
    )
    parameters = parse_and_merge_parameters(
        parameters_raw,
        args.parameter_overrides_json,
    )

    dep_id = find_deployment_id(selected)
    created = create_flow_run(
        dep_id,
        {**parameters, "resume_key": args.resume_key, "checkpoint_dir": args.checkpoint_dir},
        flow_run_name=str(parameters.get("job_name") or "") or None,
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
