from __future__ import annotations

import dataclasses
import os
from typing import Any

from prefect.context import get_run_context
from prefect.runtime import flow_run

import prefect
from flows.checkpoint_store import (
    load_checkpoint,
    resolve_checkpoint_path,
    save_checkpoint,
)
from flows.engine_run.models import FlowResult
from flows.engine_run.runtime_finalize import (
    cleanup_workdir_state,
    finalize_flow_result,
    log_core_upload,
    log_engine_upload,
    persist_engine_upload_state,
)
from flows.engine_run.runtime_logging import (
    flow_logger,
    log_checkpoint_loaded,
    log_flow_start,
)
from flows.engine_run.runtime_state import (
    flow_attempt,
    prepare_flow_state,
    record_entrypoint_state,
)
from flows.engine_run.state.main import artifact_paths_exist, build_flow_result
from flows.engine_run.task.main import (
    prepare_manifest_task,
    resolve_commit_task,
    run_entrypoint_job_task,
    upload_engine_artifacts_task,
    upload_outputs_task,
)
from flows.adapters.inbound.schema import validate_run_request
from runner import cleanup_workdir


def _flow_attempt() -> int:
    return flow_attempt(get_run_context)

@prefect.flow(name="e2e-job", retries=3, retry_delay_seconds=30)
def run_job_flow(
    *,
    run_mode: str = "repo",
    engine: str,
    entrypoint: list[str],
    repo_url: str | None = None,
    ref: str | None = None,
    config: str | None = None,
    job_name: str | None = None,
    inputs: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    outputs_prefix: str | None = None,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> FlowResult:
    logger = flow_logger()
    run_id = flow_run.get_id() or "unknown-flow-run"
    request = validate_run_request(
        {
            "run_mode": run_mode,
            "engine": engine,
            "entrypoint": entrypoint,
            "repo_url": repo_url,
            "ref": ref,
            "config": config,
            "job_name": job_name,
            "inputs": inputs or {},
            "env": env or {},
            "outputs_prefix": outputs_prefix,
        }
    )
    log_flow_start(logger, run_id=run_id, job=request)
    active_resume_key = resume_key or run_id
    checkpoint_path = resolve_checkpoint_path(
        checkpoint_dir=checkpoint_dir or os.getenv("ORCHESTRATOR_CHECKPOINT_DIR"),
        resume_key=active_resume_key,
    )
    attempt = _flow_attempt()
    attempt, state, resolved_commit = prepare_flow_state(
        checkpoint_path=checkpoint_path,
        flow_run_id=run_id,
        resume_key=active_resume_key,
        attempt=attempt,
        job=request,
        logger=logger,
        resolve_commit_task=resolve_commit_task,
        load_checkpoint_fn=load_checkpoint,
        save_checkpoint_fn=save_checkpoint,
        log_checkpoint_loaded_fn=log_checkpoint_loaded,
    )
    if state.is_step_done("run_entrypoint") and not artifact_paths_exist(
        state.local_paths
    ):
        state = state.reset_after_missing_artifacts()
        save_checkpoint(checkpoint_path, state)
    if state.is_step_done("run_entrypoint"):
        local_paths = state.local_paths
        exit_code = int(state.exit_code if state.exit_code is not None else 1)
    else:
        effective_outputs_prefix = (
            request.outputs_prefix or f"jobs/{run_id}/attempt-{attempt}/"
        )
        local_paths, exit_code = run_entrypoint_job_task(
            repo_url=request.repo_url,
            ref=request.ref,
            resolved_commit=resolved_commit,
            entrypoint=request.entrypoint,
            env=request.env,
            run_mode=request.run_mode,
            engine=request.engine,
            config_rel_path=request.config,
            inputs=request.inputs,
            flow_run_id=run_id,
            attempt=attempt,
            outputs_prefix=effective_outputs_prefix,
            job_name=request.job_name,
        )
        state = record_entrypoint_state(
            logger=logger,
            state=state,
            checkpoint_path=checkpoint_path,
            flow_run_id=run_id,
            attempt=attempt,
            local_paths=local_paths,
            exit_code=exit_code,
            save_checkpoint_fn=save_checkpoint,
        )

    if state.is_step_done("manifest_uploaded"):
        uploaded = state.uploaded
    else:
        links = prepare_manifest_task(run_id, attempt)
        state = state.mark_step("prepare_manifest")
        state = dataclasses.replace(state, links=links)
        save_checkpoint(checkpoint_path, state)

        uploaded = upload_outputs_task(
            links,
            local_paths,
            run_id,
            attempt,
            already_uploaded=state.uploaded,
        )
        log_core_upload(logger, flow_run_id=run_id, attempt=attempt, uploaded=uploaded)
        state = dataclasses.replace(state, uploaded=uploaded)
        for key in ("stdout", "stderr", "result", "manifest"):
            if key in uploaded:
                state = state.mark_step(f"{key}_uploaded")
        save_checkpoint(checkpoint_path, state)

    if exit_code == 0:
        if state.is_step_done("engine_manifest_uploaded"):
            engine_uploaded = state.engine_uploaded
            engine_manifest_uri = state.engine_manifest_uri
        else:
            engine_upload = upload_engine_artifacts_task(
                local_paths,
                run_id,
                attempt,
                exit_code,
                already_uploaded=state.engine_uploaded,
                mlflow_tags_written=state.is_step_done("engine_mlflow_tags_written"),
            )
            engine_uploaded = engine_upload.artifact_uris
            engine_manifest_uri = engine_upload.engine_manifest_uri
            log_engine_upload(
                logger,
                flow_run_id=run_id,
                attempt=attempt,
                engine_manifest_uri=engine_manifest_uri,
                engine_uploaded=engine_uploaded,
            )
            state = persist_engine_upload_state(
                state=state,
                checkpoint_path=checkpoint_path,
                engine_uploaded=engine_uploaded,
                engine_manifest_uri=engine_manifest_uri,
                mlflow_tags_written=engine_upload.mlflow_tags_written,
                save_checkpoint_fn=save_checkpoint,
            )
    else:
        engine_uploaded = state.engine_uploaded
        engine_manifest_uri = state.engine_manifest_uri

    state = cleanup_workdir_state(
        logger=logger,
        local_paths=local_paths,
        state=state,
        checkpoint_path=checkpoint_path,
        flow_run_id=run_id,
        save_checkpoint_fn=save_checkpoint,
        cleanup_workdir_fn=cleanup_workdir,
    )
    return finalize_flow_result(
        logger=logger,
        run_id=run_id,
        attempt=attempt,
        build_flow_result=build_flow_result,
        engine=request.engine,
        run_mode=request.run_mode,
        job_name=request.job_name,
        exit_code=exit_code,
        resolved_commit=resolved_commit,
        outputs_prefix=request.outputs_prefix or f"jobs/{run_id}/attempt-{attempt}/",
        uploaded=uploaded,
        engine_manifest_uri=engine_manifest_uri or "",
        engine_uploaded=engine_uploaded,
    )
engine_run_flow = run_job_flow
