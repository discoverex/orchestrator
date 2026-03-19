from __future__ import annotations

import dataclasses
from typing import Any

from flows.engine_run.runtime_finalize import (
    log_core_upload,
    log_engine_upload,
    persist_engine_upload_state,
)


def upload_core_outputs(
    *,
    logger: Any,
    state: Any,
    checkpoint_path: Any,
    run_id: str,
    attempt: int,
    local_paths: Any,
    prepare_manifest_task: Any,
    upload_outputs_task: Any,
    save_checkpoint_fn: Any,
) -> tuple[Any, dict[str, str]]:
    if state.is_step_done("manifest_uploaded"):
        return state, state.uploaded

    links = prepare_manifest_task(run_id, attempt)
    state = state.mark_step("prepare_manifest")
    state = dataclasses.replace(state, links=links)
    save_checkpoint_fn(checkpoint_path, state)

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
    save_checkpoint_fn(checkpoint_path, state)
    return state, uploaded


def upload_engine_outputs(
    *,
    logger: Any,
    state: Any,
    checkpoint_path: Any,
    local_paths: Any,
    run_id: str,
    attempt: int,
    exit_code: int,
    upload_engine_artifacts_task: Any,
    save_checkpoint_fn: Any,
) -> tuple[Any, dict[str, str], str]:
    if exit_code != 0:
        return state, state.engine_uploaded, state.engine_manifest_uri
    if state.is_step_done("engine_manifest_uploaded"):
        return state, state.engine_uploaded, state.engine_manifest_uri

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
        save_checkpoint_fn=save_checkpoint_fn,
    )
    return state, engine_uploaded, engine_manifest_uri
