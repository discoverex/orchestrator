from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import cast

from prefect import get_run_logger, task
from prefect.exceptions import MissingContextError

from flows.engine_run.http import http_json, storage_base_url, upload_file
from flows.engine_run.models import ArtifactLink
from runner.git_runner import resolve_commit, run_entrypoint


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
    logger = _get_task_logger()
    gateway = storage_base_url()
    payload = {
        "flow_run_id": flow_run_id,
        "attempt": attempt,
        "entries": [
            {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "kind": "stdout",
                "filename": "stdout.log",
            },
            {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "kind": "stderr",
                "filename": "stderr.log",
            },
            {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "kind": "result",
                "filename": "result.json",
            },
            {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "kind": "manifest",
                "filename": "artifacts.json",
            },
        ],
    }
    rows = http_json("POST", f"{gateway}/v1/presign/batch", payload)
    assert isinstance(rows, list)
    links = [
        ArtifactLink(
            kind=str(r["kind"]), object_uri=str(r["object_uri"]), url=str(r["url"])
        )
        for r in rows
    ]
    logger.info(
        "issued artifact links: %s",
        [
            {"kind": link.kind, "object_uri": link.object_uri, "url": link.url}
            for link in links
        ],
    )
    return links


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
    paths = {
        "workdir": str(artifacts.workdir),
        "stdout": str(artifacts.stdout_path),
        "stderr": str(artifacts.stderr_path),
        "result": str(artifacts.result_path),
    }
    return paths, artifacts.exit_code


@task(retries=2, retry_delay_seconds=10)
def upload_outputs_task(
    links: list[ArtifactLink],
    local_paths: dict[str, str],
    flow_run_id: str,
    attempt: int,
    already_uploaded: dict[str, str] | None = None,
) -> dict[str, str]:
    logger = _get_task_logger()
    output: dict[str, str] = dict(already_uploaded or {})
    for link in links:
        if link.kind in output:
            continue
        if link.kind == "manifest":
            manifest = {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "artifacts": [
                    {"kind": k, "object_uri": v}
                    for k, v in output.items()
                    if k != "manifest"
                ],
            }
            manifest_path = Path(local_paths["result"]).parent / "artifacts.json"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8"
            )
            logger.info(
                "uploading manifest artifact: kind=%s object_uri=%s url=%s",
                link.kind,
                link.object_uri,
                link.url,
            )
            upload_file(link.url, manifest_path.read_bytes())
            output["manifest"] = link.object_uri
            continue

        src = Path(local_paths[link.kind])
        logger.info(
            "uploading artifact: kind=%s object_uri=%s url=%s local_path=%s",
            link.kind,
            link.object_uri,
            link.url,
            src,
        )
        upload_file(link.url, src.read_bytes())
        output[link.kind] = link.object_uri
    return output
