from __future__ import annotations

import logging
from typing import cast

from prefect.exceptions import MissingContextError

from flows.engine_run.models import ArtifactLink
from flows.engine_run.task.engine_artifacts import (
    EngineArtifactsUploadResult,
    upload_engine_artifacts,
)
from flows.engine_run.task.support import mlflow_post as _mlflow_post
from flows.engine_run.task.uploads import prepare_manifest_links, upload_outputs
from flows.engine_run.utils.http import http_json, storage_base_url, upload_file
from prefect import get_run_logger, task
from runner.git.runner import resolve_commit, run_entrypoint


def _get_task_logger() -> logging.Logger:
    try:
        return cast(logging.Logger, get_run_logger())
    except MissingContextError:
        return logging.getLogger("flows.engine_run.tasks")


@task
def resolve_commit_task(repo_url: str, ref: str) -> str:
    return resolve_commit(repo_url, ref)


@task
def prepare_manifest_task(flow_run_id: str, attempt: int) -> list[ArtifactLink]:
    return prepare_manifest_links(
        flow_run_id,
        attempt,
        logger=_get_task_logger(),
        http_json_fn=http_json,
        storage_base_url_fn=storage_base_url,
    )


@task
def run_entrypoint_task(
    repo_url: str, resolved_commit: str, entrypoint: list[str], env: dict[str, str]
) -> tuple[dict[str, str], int]:
    raise RuntimeError(
        "run_entrypoint_task signature changed; call run_entrypoint_job_task instead"
    )


@task
def run_entrypoint_job_task(
    *,
    repo_url: str | None,
    ref: str | None,
    resolved_commit: str | None,
    entrypoint: list[str],
    env: dict[str, str],
    run_mode: str = "repo",
    engine: str,
    config_rel_path: str | None,
    inputs: dict[str, object],
    flow_run_id: str,
    attempt: int,
    outputs_prefix: str,
    job_name: str | None = None,
) -> tuple[dict[str, str], int]:
    artifacts = run_entrypoint(
        repo_url=repo_url,
        ref=ref,
        resolved_commit=resolved_commit,
        entrypoint=entrypoint,
        env=env,
        run_mode=run_mode,
        engine=engine,
        config_rel_path=config_rel_path,
        inputs=inputs,
        flow_run_id=flow_run_id,
        attempt=attempt,
        outputs_prefix=outputs_prefix,
        job_name=job_name,
    )
    return (
        {
            "workdir": str(artifacts.workdir),
            "stdout": str(artifacts.stdout_path),
            "stderr": str(artifacts.stderr_path),
            "result": str(artifacts.result_path),
            "engine_artifact_dir": str(artifacts.engine_artifact_dir),
            "engine_artifact_manifest": str(artifacts.engine_artifact_manifest_path),
        },
        artifacts.exit_code,
    )


@task(retries=2, retry_delay_seconds=10)
def upload_outputs_task(
    links: list[ArtifactLink],
    local_paths: dict[str, str],
    flow_run_id: str,
    attempt: int,
    already_uploaded: dict[str, str] | None = None,
) -> dict[str, str]:
    return upload_outputs(
        links,
        local_paths,
        flow_run_id,
        attempt,
        logger=_get_task_logger(),
        upload_file_fn=upload_file,
        already_uploaded=already_uploaded,
    )


@task(retries=2, retry_delay_seconds=10)
def upload_engine_artifacts_task(
    local_paths: dict[str, str],
    flow_run_id: str,
    attempt: int,
    exit_code: int,
    already_uploaded: dict[str, str] | None = None,
    mlflow_tags_written: bool = False,
) -> EngineArtifactsUploadResult:
    return upload_engine_artifacts(
        local_paths,
        flow_run_id,
        attempt,
        exit_code,
        logger=_get_task_logger(),
        http_json_fn=http_json,
        storage_base_url_fn=storage_base_url,
        upload_file_fn=upload_file,
        mlflow_post_fn=_mlflow_post,
        already_uploaded=already_uploaded,
        mlflow_tags_written=mlflow_tags_written,
    )
