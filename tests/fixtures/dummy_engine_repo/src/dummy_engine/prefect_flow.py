from __future__ import annotations

from typing import Any

from flows.engine_run.flow import run_job_flow as orchestrator_run_job_flow
from flows.engine_run.models import FlowResult
from prefect import flow


@flow(name="e2e-job", retries=3, retry_delay_seconds=30)
def run_job_flow(
    job_spec_json: str | dict[str, Any],
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> FlowResult:
    return orchestrator_run_job_flow.fn(
        job_spec_json,
        resume_key=resume_key,
        checkpoint_dir=checkpoint_dir,
    )


dummy_engine_flow = run_job_flow
