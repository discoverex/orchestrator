#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib import error, request


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _prefect_api_url() -> str:
    return _env("PREFECT_API_URL", "http://127.0.0.1:4200/api").rstrip("/")


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "orchestrator-router/1.0",
    }
    cf_id = _env("PREFECT_CF_ACCESS_CLIENT_ID")
    cf_secret = _env("PREFECT_CF_ACCESS_CLIENT_SECRET")
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _http_json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    url = f"{_prefect_api_url()}/{path.lstrip('/')}"
    body = None
    headers = _headers()
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, method=method, data=body, headers=headers)
    try:
        with request.urlopen(req, timeout=30) as resp:  # nosec B310 - controlled URL via env
            raw = resp.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class QueueDepth:
    queue_name: str
    scheduled_count: int
    running_count: int


def _count_for_queue(queue_name: str, state_types: list[str], max_rows: int = 200) -> int:
    rows = _http_json(
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
    if not isinstance(rows, list):
        return 0
    return len(rows)


def _scheduled_count_for_queue(queue_name: str, max_rows: int = 200) -> int:
    return _count_for_queue(queue_name, ["SCHEDULED", "PENDING"], max_rows=max_rows)


def _running_count_for_queue(queue_name: str, max_rows: int = 200) -> int:
    return _count_for_queue(queue_name, ["RUNNING"], max_rows=max_rows)


def _find_deployment_id(deployment_name: str) -> str:
    rows = _http_json(
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


def _create_flow_run(deployment_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
    row = _http_json(
        "POST",
        f"deployments/{deployment_id}/create_flow_run",
        {"parameters": parameters},
    )
    if not isinstance(row, dict):
        raise RuntimeError("unexpected create_flow_run response shape")
    return row


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Submit flow run to fixed/colab deployment based on queue-depth policy.")
    parser.add_argument("--mode", default=_env("WORKER_ROUTING_MODE", "fixed-first"), choices=("fixed-first", "colab-first"))
    parser.add_argument(
        "--strict-priority",
        default=_env("WORKER_ROUTING_STRICT_PRIORITY", "false"),
        help="If true, always submit to preferred deployment and never divert by backlog.",
    )
    parser.add_argument(
        "--queue-depth-threshold",
        type=int,
        default=int(_env("WORKER_ROUTING_QUEUE_DEPTH_THRESHOLD", "1")),
        help="Backlog threshold to divert to the non-preferred deployment when strict-priority is false.",
    )
    parser.add_argument(
        "--divert-when-running",
        default=_env("WORKER_ROUTING_DIVERT_WHEN_RUNNING", "true"),
        help="If true and preferred queue has RUNNING flow(s), divert to secondary when strict-priority is false.",
    )
    parser.add_argument("--fixed-deployment", default=_env("ROUTER_FIXED_DEPLOYMENT", "engine-run"))
    parser.add_argument("--colab-deployment", default=_env("ROUTER_COLAB_DEPLOYMENT", "engine-run-colab"))
    parser.add_argument("--fixed-queue", default=_env("ROUTER_FIXED_QUEUE", "gpu-fixed"))
    parser.add_argument("--colab-queue", default=_env("ROUTER_COLAB_QUEUE", "gpu-colab"))
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--ref", default="main")
    parser.add_argument("--entrypoint", default='["/bin/sh","-lc","echo hello-from-router"]')
    parser.add_argument("--resume-key", default=None)
    parser.add_argument("--checkpoint-dir", default=None)
    parser.add_argument("--parameters-json", default=None, help="Optional JSON object merged into deployment parameters.")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    strict_priority = _parse_bool(args.strict_priority)
    divert_when_running = _parse_bool(args.divert_when_running)
    if args.queue_depth_threshold < 0:
        raise SystemExit("--queue-depth-threshold must be >= 0")

    fixed_depth = QueueDepth(
        queue_name=args.fixed_queue,
        scheduled_count=_scheduled_count_for_queue(args.fixed_queue),
        running_count=_running_count_for_queue(args.fixed_queue),
    )
    colab_depth = QueueDepth(
        queue_name=args.colab_queue,
        scheduled_count=_scheduled_count_for_queue(args.colab_queue),
        running_count=_running_count_for_queue(args.colab_queue),
    )

    preferred_deployment = args.fixed_deployment if args.mode == "fixed-first" else args.colab_deployment
    secondary_deployment = args.colab_deployment if args.mode == "fixed-first" else args.fixed_deployment
    preferred_depth = fixed_depth if args.mode == "fixed-first" else colab_depth

    selected = preferred_deployment
    decision_reason = "strict-priority-selected-preferred" if strict_priority else "preferred-selected"
    if not strict_priority:
        if divert_when_running and preferred_depth.running_count > 0:
            selected = secondary_deployment
            decision_reason = "running-diverted-to-secondary"
        elif preferred_depth.scheduled_count > args.queue_depth_threshold:
            selected = secondary_deployment
            decision_reason = "backlog-diverted-to-secondary"

    params: dict[str, Any] = {
        "repo_url": args.repo_url,
        "ref": args.ref,
        "entrypoint": json.loads(args.entrypoint),
        "resume_key": args.resume_key,
        "checkpoint_dir": args.checkpoint_dir,
    }
    if args.parameters_json:
        extra = json.loads(args.parameters_json)
        if not isinstance(extra, dict):
            raise SystemExit("--parameters-json must be a JSON object")
        params.update(extra)

    dep_id = _find_deployment_id(selected)
    created = _create_flow_run(dep_id, params)

    output = {
        "ok": True,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "mode": args.mode,
        "strict_priority": strict_priority,
        "divert_when_running": divert_when_running,
        "queue_depth_threshold": args.queue_depth_threshold,
        "fixed_queue_depth": fixed_depth.scheduled_count,
        "fixed_queue_running": fixed_depth.running_count,
        "colab_queue_depth": colab_depth.scheduled_count,
        "colab_queue_running": colab_depth.running_count,
        "selected_deployment": selected,
        "selected_deployment_id": dep_id,
        "reason": decision_reason,
        "flow_run_id": created.get("id"),
        "flow_run_name": created.get("name"),
    }
    print(json.dumps(output, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
