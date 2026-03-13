from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from flows.job_spec import JobSpecError, parse_job_spec_json


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class QueueDepth:
    queue_name: str
    scheduled_count: int
    running_count: int


@dataclass(frozen=True)
class RouteDecision:
    selected_deployment: str
    reason: str


def select_deployment(
    *,
    mode: str,
    strict_priority: bool,
    divert_when_running: bool,
    queue_depth_threshold: int,
    fixed_deployment: str,
    colab_deployment: str,
    fixed_depth: QueueDepth,
    colab_depth: QueueDepth,
) -> RouteDecision:
    preferred = fixed_deployment if mode == "fixed-first" else colab_deployment
    secondary = colab_deployment if mode == "fixed-first" else fixed_deployment
    preferred_depth = fixed_depth if mode == "fixed-first" else colab_depth
    if strict_priority:
        return RouteDecision(preferred, "strict-priority-selected-preferred")
    if divert_when_running and preferred_depth.running_count > 0:
        return RouteDecision(secondary, "running-diverted-to-secondary")
    if preferred_depth.scheduled_count > queue_depth_threshold:
        return RouteDecision(secondary, "backlog-diverted-to-secondary")
    return RouteDecision(preferred, "preferred-selected")


def parse_and_merge_job_spec(
    job_spec_raw: str, parameters_json: str | None
) -> dict[str, Any]:
    try:
        job_spec = asdict(parse_job_spec_json(job_spec_raw))
    except JobSpecError as exc:
        raise SystemExit(str(exc)) from exc
    if not parameters_json:
        return {"job_spec": job_spec, "job_spec_raw": job_spec_raw}
    extra = json.loads(parameters_json)
    if not isinstance(extra, dict):
        raise SystemExit("--parameters-json must be a JSON object")
    job_spec.update(extra)
    merged_raw = json.dumps(job_spec, ensure_ascii=True)
    try:
        parse_job_spec_json(merged_raw)
    except JobSpecError as exc:
        raise SystemExit(f"invalid merged job spec: {exc}") from exc
    return {"job_spec": job_spec, "job_spec_raw": merged_raw}
