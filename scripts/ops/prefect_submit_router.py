#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request

from pydantic import BaseModel, ConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from flows.job_spec import JobSpecError, parse_job_spec_json  # noqa: E402


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _prefect_api_url() -> str:
    return _env("PREFECT_API_URL", "http://127.0.0.1:4200/api").rstrip("/")


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "orchestrator-router/1.0",
    }
    cf_id = _env("CF_ACCESS_CLIENT_ID")
    cf_secret = _env("CF_ACCESS_CLIENT_SECRET")
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


class QueueDepth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    queue_name: str
    scheduled_count: int
    running_count: int


def _count_for_queue(
    queue_name: str, state_types: list[str], max_rows: int = 200
) -> int:
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


def _create_flow_run(
    deployment_id: str, parameters: dict[str, Any], flow_run_name: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"parameters": parameters}
    if flow_run_name:
        payload["name"] = flow_run_name
    row = _http_json(
        "POST",
        f"deployments/{deployment_id}/create_flow_run",
        payload,
    )
    if not isinstance(row, dict):
        raise RuntimeError("unexpected create_flow_run response shape")
    return row


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit flow run to fixed/colab deployment based on queue-depth policy."
    )
    parser.add_argument(
        "--mode",
        default=_env("WORKER_ROUTING_MODE", "fixed-first"),
        choices=("fixed-first", "colab-first"),
    )
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
    parser.add_argument(
        "--fixed-deployment", default=_env("ROUTER_FIXED_DEPLOYMENT", "engine-run")
    )
    parser.add_argument(
        "--colab-deployment",
        default=_env("ROUTER_COLAB_DEPLOYMENT", "engine-run-colab"),
    )
    parser.add_argument(
        "--fixed-queue", default=_env("ROUTER_FIXED_QUEUE", "gpu-fixed")
    )
    parser.add_argument(
        "--colab-queue", default=_env("ROUTER_COLAB_QUEUE", "gpu-colab")
    )
    parser.add_argument("--job-spec-json", default=None, help="JobSpec JSON string.")
    parser.add_argument(
        "--job-spec-file", default=None, help="Path to JobSpec JSON file."
    )
    parser.add_argument("--resume-key", default=None)
    parser.add_argument("--checkpoint-dir", default=None)
    parser.add_argument(
        "--parameters-json",
        default=None,
        help="Optional JSON object merged into JobSpec JSON.",
    )
    return parser


def _load_job_spec_raw(args: argparse.Namespace) -> str:
    if bool(args.job_spec_json) == bool(args.job_spec_file):
        raise SystemExit(
            "exactly one of --job-spec-json or --job-spec-file is required"
        )
    if args.job_spec_json:
        return str(args.job_spec_json)
    return Path(str(args.job_spec_file)).read_text(encoding="utf-8")


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

    preferred_deployment = (
        args.fixed_deployment if args.mode == "fixed-first" else args.colab_deployment
    )
    secondary_deployment = (
        args.colab_deployment if args.mode == "fixed-first" else args.fixed_deployment
    )
    preferred_depth = fixed_depth if args.mode == "fixed-first" else colab_depth

    selected = preferred_deployment
    decision_reason = (
        "strict-priority-selected-preferred"
        if strict_priority
        else "preferred-selected"
    )
    if not strict_priority:
        if divert_when_running and preferred_depth.running_count > 0:
            selected = secondary_deployment
            decision_reason = "running-diverted-to-secondary"
        elif preferred_depth.scheduled_count > args.queue_depth_threshold:
            selected = secondary_deployment
            decision_reason = "backlog-diverted-to-secondary"

    job_spec_raw = _load_job_spec_raw(args)
    try:
        job_spec = parse_job_spec_json(job_spec_raw).model_dump(mode="json")
    except JobSpecError as exc:
        raise SystemExit(str(exc)) from exc
    if args.parameters_json:
        extra = json.loads(args.parameters_json)
        if not isinstance(extra, dict):
            raise SystemExit("--parameters-json must be a JSON object")
        job_spec.update(extra)
        job_spec_raw = json.dumps(job_spec, ensure_ascii=True)
        try:
            parse_job_spec_json(job_spec_raw)
        except JobSpecError as exc:
            raise SystemExit(f"invalid merged job spec: {exc}") from exc

    dep_id = _find_deployment_id(selected)
    params: dict[str, Any] = {
        "job_spec_json": job_spec_raw,
        "resume_key": args.resume_key,
        "checkpoint_dir": args.checkpoint_dir,
    }
    created = _create_flow_run(dep_id, params, flow_run_name=job_spec.get("job_name"))

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
        "engine": job_spec.get("engine"),
        "reason": decision_reason,
        "flow_run_id": created.get("id"),
        "flow_run_name": created.get("name"),
    }
    print(json.dumps(output, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
