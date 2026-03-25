from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flows.engine_run.models import FlowResult, FlowState


def log_core_upload(
    logger: Any, *, flow_run_id: str, attempt: int, uploaded: dict[str, str]
) -> None:
    logger.info(
        "core output upload finished",
        extra={
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "uploaded_keys": sorted(uploaded.keys()),
        },
    )


def log_engine_upload(
    logger: Any,
    *,
    flow_run_id: str,
    attempt: int,
    engine_manifest_uri: str,
    engine_uploaded: dict[str, str],
) -> None:
    logger.info(
        "engine artifact upload finished",
        extra={
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "engine_manifest_uri": engine_manifest_uri or "",
            "engine_artifact_count": len(engine_uploaded),
        },
    )


def cleanup_workdir_state(
    *,
    logger: Any,
    local_paths: dict[str, str],
    state: FlowState,
    checkpoint_path: Path | None,
    flow_run_id: str,
    save_checkpoint_fn: Callable[[Path | None, FlowState], None],
    cleanup_workdir_fn: Callable[[Path], None],
) -> FlowState:
    workdir_raw = local_paths.get("workdir")
    if not workdir_raw:
        return state
    workdir = Path(workdir_raw)
    if state.is_step_done("cleanup") or not workdir.exists():
        return state
    cleanup_workdir_fn(workdir)
    state = state.mark_step("cleanup")
    save_checkpoint_fn(checkpoint_path, state)
    logger.info(
        "workdir cleanup finished",
        extra={"flow_run_id": flow_run_id, "workdir": str(workdir)},
    )
    return state


def persist_engine_upload_state(
    *,
    state: FlowState,
    checkpoint_path: Path | None,
    engine_uploaded: dict[str, str],
    engine_manifest_uri: str | None,
    mlflow_tags_written: bool,
    save_checkpoint_fn: Callable[[Path | None, FlowState], None],
) -> FlowState:
    state = dataclasses.replace(
        state,
        engine_uploaded=engine_uploaded,
        engine_manifest_uri=engine_manifest_uri,
    )
    state = state.mark_step("engine_artifacts_uploaded")
    if engine_manifest_uri:
        state = state.mark_step("engine_manifest_uploaded")
    if mlflow_tags_written:
        state = state.mark_step("engine_mlflow_tags_written")
    save_checkpoint_fn(checkpoint_path, state)
    return state


def finalize_flow_result(
    *,
    logger: Any,
    build_flow_result: Callable[..., FlowResult],
    run_id: str,
    attempt: int,
    engine: str,
    run_mode: str,
    job_name: str | None,
    resolved_commit: str,
    outputs_prefix: str,
    uploaded: dict[str, str],
    engine_manifest_uri: str | None,
    engine_uploaded: dict[str, str],
    exit_code: int,
) -> FlowResult:
    result = build_flow_result(
        flow_run_id=run_id,
        attempt=attempt,
        engine=engine,
        run_mode=run_mode,
        job_name=job_name,
        resolved_commit=resolved_commit,
        outputs_prefix=outputs_prefix,
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
