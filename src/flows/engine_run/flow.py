from __future__ import annotations

import dataclasses
import logging
import os
from pathlib import Path
from typing import Any

from prefect.context import get_run_context
from prefect.runtime import flow_run

from flows.checkpoint_store import (
    load_checkpoint,
    resolve_checkpoint_path,
    save_checkpoint,
)
from flows.engine_run.models import FlowResult, FlowState
from flows.engine_run.state.main import (
    artifact_paths_exist,
    build_flow_result,
)
from flows.engine_run.task.main import (
    prepare_manifest_task,
    resolve_commit_task,
    run_entrypoint_job_task,
    upload_engine_artifacts_task,
    upload_outputs_task,
)
from flows.job_spec import parse_job_spec_json
from prefect import flow, get_run_logger
from runner import cleanup_workdir


def _flow_logger() -> logging.Logger:
    try:
        return get_run_logger()
    except Exception:
        return logging.getLogger("flows.engine_run.flow")


def _flow_attempt() -> int:
    try:
        ctx = get_run_context()
        flow_ctx = getattr(ctx, "flow_run", None)
        run_count = getattr(flow_ctx, "run_count", None)
        return int(run_count or 1)
    except Exception:
        return 1


@flow(name="e2e-job", retries=3, retry_delay_seconds=30)
def run_job_flow(
    job_spec_json: str | dict[str, Any],
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> FlowResult:
    logger = _flow_logger()
    run_id = flow_run.get_id() or "unknown-flow-run"
    if isinstance(job_spec_json, dict):
        import json

        job_spec_raw = json.dumps(job_spec_json, ensure_ascii=True)
    else:
        job_spec_raw = job_spec_json
    job = parse_job_spec_json(job_spec_raw)
    logger.info(
        "run_job_flow started",
        extra={
            "flow_run_id": run_id,
            "engine": job.engine,
            "run_mode": job.run_mode,
            "repo_url": job.repo_url or "",
            "ref": job.ref or "",
            "job_name": job.job_name or "",
        },
    )
    active_resume_key = resume_key or run_id
    checkpoint_path = resolve_checkpoint_path(
        checkpoint_dir=checkpoint_dir or os.getenv("ORCHESTRATOR_CHECKPOINT_DIR"),
        resume_key=active_resume_key,
    )

    attempt = _flow_attempt()
    state = load_checkpoint(checkpoint_path, FlowState)
    if state is None:
        state = FlowState(
            flow_run_id=run_id,
            resume_key=active_resume_key,
            attempt=attempt,
        )
    else:
        state = dataclasses.replace(state, attempt=attempt)
    save_checkpoint(checkpoint_path, state)
    logger.info(
        "checkpoint state loaded",
        extra={
            "flow_run_id": run_id,
            "attempt": attempt,
            "checkpoint_path": str(checkpoint_path),
            "resume_key": active_resume_key,
        },
    )

    if job.run_mode == "inline":
        resolved_commit = "inline"
        state = dataclasses.replace(state, resolved_commit=resolved_commit)
        state = state.mark_step("resolve_commit")
        save_checkpoint(checkpoint_path, state)
    elif state.is_step_done("resolve_commit"):
        resolved_commit = str(state.resolved_commit)
    else:
        if not job.repo_url or not job.ref:
            raise RuntimeError("repo_url/ref required for run_mode=repo")
        resolved_commit = resolve_commit_task(job.repo_url, job.ref)
        logger.info(
            "resolved commit for job",
            extra={
                "flow_run_id": run_id,
                "repo_url": job.repo_url,
                "ref": job.ref,
                "resolved_commit": resolved_commit,
            },
        )
        state = dataclasses.replace(state, resolved_commit=resolved_commit)
        state = state.mark_step("resolve_commit")
        save_checkpoint(checkpoint_path, state)

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
            job.outputs_prefix or f"jobs/{run_id}/attempt-{attempt}/"
        )
        local_paths, exit_code = run_entrypoint_job_task(
            repo_url=job.repo_url,
            ref=job.ref,
            resolved_commit=resolved_commit,
            entrypoint=job.entrypoint,
            env=job.env,
            run_mode=job.run_mode,
            engine=job.engine,
            config_rel_path=job.config,
            inputs=job.inputs,
            flow_run_id=run_id,
            attempt=attempt,
            outputs_prefix=effective_outputs_prefix,
            job_name=job.job_name,
        )
        logger.info(
            "entrypoint execution finished",
            extra={
                "flow_run_id": run_id,
                "attempt": attempt,
                "exit_code": exit_code,
                "workdir": local_paths.get("workdir", ""),
            },
        )
        state = dataclasses.replace(state, local_paths=local_paths, exit_code=exit_code)
        state = state.mark_step("run_entrypoint")
        new_steps = dict(state.steps)
        new_steps["cleanup"] = False
        state = dataclasses.replace(state, steps=new_steps)
        save_checkpoint(checkpoint_path, state)

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
        logger.info(
            "core output upload finished",
            extra={
                "flow_run_id": run_id,
                "attempt": attempt,
                "uploaded_keys": sorted(uploaded.keys()),
            },
        )
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
            logger.info(
                "engine artifact upload finished",
                extra={
                    "flow_run_id": run_id,
                    "attempt": attempt,
                    "engine_manifest_uri": engine_manifest_uri or "",
                    "engine_artifact_count": len(engine_uploaded),
                },
            )
            state = dataclasses.replace(
                state,
                engine_uploaded=engine_uploaded,
                engine_manifest_uri=engine_manifest_uri,
            )
            state = state.mark_step("engine_artifacts_uploaded")
            if engine_manifest_uri:
                state = state.mark_step("engine_manifest_uploaded")
            if engine_upload.mlflow_tags_written:
                state = state.mark_step("engine_mlflow_tags_written")
            save_checkpoint(checkpoint_path, state)
    else:
        engine_uploaded = state.engine_uploaded
        engine_manifest_uri = state.engine_manifest_uri

    workdir_raw = local_paths.get("workdir")
    if workdir_raw:
        workdir = Path(workdir_raw)
        if not state.is_step_done("cleanup") and workdir.exists():
            cleanup_workdir(workdir)
            state = state.mark_step("cleanup")
            save_checkpoint(checkpoint_path, state)
            logger.info(
                "workdir cleanup finished",
                extra={"flow_run_id": run_id, "workdir": str(workdir)},
            )

    result = build_flow_result(
        flow_run_id=run_id,
        attempt=attempt,
        engine=job.engine,
        run_mode=job.run_mode,
        job_name=job.job_name,
        resolved_commit=resolved_commit,
        outputs_prefix=job.outputs_prefix or f"jobs/{run_id}/attempt-{attempt}/",
        uploaded=uploaded,
        engine_manifest_uri=engine_manifest_uri,
        engine_uploaded=engine_uploaded,
        exit_code=exit_code,
    )
    logger.info(
        "run_job_flow finished",
        extra={
            "flow_run_id": run_id,
            "attempt": attempt,
            "exit_code": exit_code,
            "resolved_commit": resolved_commit,
        },
    )
    return result


engine_run_flow = run_job_flow
