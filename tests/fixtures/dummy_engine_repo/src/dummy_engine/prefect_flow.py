from __future__ import annotations

from typing import Any

from flows.engine_run.models import FlowResult
from flows.worker_runtime.flow import run_worker_job_flow
from prefect import flow


@flow(name="dummy-engine-job", retries=3, retry_delay_seconds=30)
def dummy_engine_flow(
    job_spec_json: str | dict[str, Any],
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> FlowResult:
    return run_worker_job_flow.fn(
        job_spec_json,
        resume_key=resume_key,
        checkpoint_dir=checkpoint_dir,
    )


run_job_flow = dummy_engine_flow
