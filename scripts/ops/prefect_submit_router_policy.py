from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from flows.adapters.inbound.schema import RunRequestError, load_parameters_json


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


def parse_and_merge_parameters(
    parameters_raw: str, overrides_json: str | None
) -> dict[str, Any]:
    try:
        parameters = json.loads(parameters_raw)
        request = load_parameters_json(parameters_raw)
        parameters = {
            "run_mode": request.run_mode,
            "engine": request.engine,
            "repo_url": request.repo_url,
            "ref": request.ref,
            "flow_entrypoint": request.flow_entrypoint,
            "config": request.config,
            "job_name": request.job_name,
            "inputs": request.inputs,
            "env": request.env,
            "outputs_prefix": request.outputs_prefix,
        }
    except (RunRequestError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    if not overrides_json:
        return parameters
    extra = json.loads(overrides_json)
    if not isinstance(extra, dict):
        raise SystemExit("--parameters-json must be a JSON object")
    parameters.update(extra)
    try:
        load_parameters_json(json.dumps(parameters, ensure_ascii=True))
    except RunRequestError as exc:
        raise SystemExit(f"invalid merged parameters: {exc}") from exc
    return parameters
