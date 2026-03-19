from __future__ import annotations

from pathlib import Path
from typing import Any

from flows.adapters.inbound.schema import validate_run_request
from flows.checkpoint_store import resolve_checkpoint_path
from flows.domain.run_request import RunRequest


def build_run_request(
    *,
    run_mode: str,
    engine: str,
    flow_entrypoint: str,
    repo_url: str | None,
    ref: str | None,
    config: str | None,
    job_name: str | None,
    inputs: dict[str, Any] | None,
    env: dict[str, str] | None,
    outputs_prefix: str | None,
) -> RunRequest:
    return validate_run_request(
        {
            "run_mode": run_mode,
            "engine": engine,
            "flow_entrypoint": flow_entrypoint,
            "repo_url": repo_url,
            "ref": ref,
            "config": config,
            "job_name": job_name,
            "inputs": inputs or {},
            "env": env or {},
            "outputs_prefix": outputs_prefix,
        }
    )


def build_checkpoint_path(
    *, checkpoint_dir: str | None, resume_key: str | None, run_id: str
) -> tuple[str, Path | None]:
    active_resume_key = resume_key or run_id
    checkpoint_path = resolve_checkpoint_path(
        checkpoint_dir=checkpoint_dir,
        resume_key=active_resume_key,
    )
    return active_resume_key, checkpoint_path
