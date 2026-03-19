from __future__ import annotations

from flows.engine_run.models import FlowResult
from flows.worker_runtime.flow import run_worker_job_flow
from prefect import flow


@flow(name="dummy-engine-job", retries=3, retry_delay_seconds=30)
def dummy_engine_flow(
    *,
    run_mode: str = "repo",
    engine: str,
    entrypoint: list[str],
    repo_url: str | None = None,
    ref: str | None = None,
    config: str | None = None,
    job_name: str | None = None,
    inputs: dict[str, object] | None = None,
    env: dict[str, str] | None = None,
    outputs_prefix: str | None = None,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> FlowResult:
    return run_worker_job_flow.fn(
        run_mode=run_mode,
        engine=engine,
        entrypoint=entrypoint,
        repo_url=repo_url,
        ref=ref,
        config=config,
        job_name=job_name,
        inputs=inputs,
        env=env,
        outputs_prefix=outputs_prefix,
        resume_key=resume_key,
        checkpoint_dir=checkpoint_dir,
    )


run_job_flow = dummy_engine_flow
