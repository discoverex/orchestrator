from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, cast
from urllib import request

from prefect import get_run_logger, task
from prefect.exceptions import MissingContextError

from flows.engine_run.http import http_json, storage_base_url, upload_file
from flows.engine_run.models import (
    ArtifactLink,
    EngineArtifactManifest,
    EngineArtifactManifestEntry,
)
from runner.git_runner import resolve_commit, run_entrypoint


def _get_task_logger() -> logging.Logger:
    try:
        return cast(logging.Logger, get_run_logger())
    except MissingContextError:
        return logging.getLogger("flows.engine_run.tasks")


def _load_engine_artifact_manifest(
    local_paths: dict[str, str], *, require_manifest: bool
) -> tuple[EngineArtifactManifest | None, Path | None, Path]:
    artifact_dir = Path(local_paths["engine_artifact_dir"])
    manifest_path = Path(local_paths["engine_artifact_manifest"])
    if not manifest_path.exists():
        if require_manifest:
            raise RuntimeError(
                f"successful engine run must write manifest: {manifest_path}"
            )
        return None, None, artifact_dir
    payload = manifest_path.read_text(encoding="utf-8")
    manifest = EngineArtifactManifest.model_validate_json(payload)
    return manifest, manifest_path, artifact_dir


def _resolve_engine_artifact_path(
    artifact_dir: Path, entry: EngineArtifactManifestEntry
) -> Path:
    resolved = (artifact_dir / entry.relative_path).resolve()
    if not str(resolved).startswith(str(artifact_dir.resolve()) + os.sep):
        raise RuntimeError(f"engine artifact escapes artifact root: {entry.relative_path}")
    if not resolved.exists() or not resolved.is_file():
        raise RuntimeError(f"engine artifact file not found: {entry.relative_path}")
    return resolved


def _mlflow_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "orchestrator-worker/1.0",
    }
    cf_id = os.getenv("CF_ACCESS_CLIENT_ID", "").strip()
    cf_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _mlflow_post(path: str, payload: dict[str, object]) -> dict[str, Any]:
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip().rstrip("/")
    if not tracking_uri:
        raise RuntimeError("missing required environment variable: MLFLOW_TRACKING_URI")
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        f"{tracking_uri}{path}",
        method="POST",
        data=body,
        headers=_mlflow_headers(),
    )
    with request.urlopen(req, timeout=30) as resp:  # nosec B310
        raw = resp.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError("unexpected MLflow response type")
    return cast(dict[str, Any], parsed)


def _set_mlflow_tag(run_id: str, key: str, value: str) -> None:
    _mlflow_post(
        "/api/2.0/mlflow/runs/set-tag",
        {"run_id": run_id, "key": key, "value": value},
    )


def _extract_run_id_from_stdout(stdout_path: Path) -> str:
    for line in stdout_path.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        run_id = str(payload.get("mlflow_run_id", "")).strip()
        if run_id:
            return run_id
    return ""


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
        "engine_artifact_dir": str(artifacts.engine_artifact_dir),
        "engine_artifact_manifest": str(artifacts.engine_artifact_manifest_path),
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


@task(retries=2, retry_delay_seconds=10)
def upload_engine_artifacts_task(
    local_paths: dict[str, str],
    flow_run_id: str,
    attempt: int,
    exit_code: int,
    already_uploaded: dict[str, str] | None = None,
    mlflow_tags_written: bool = False,
) -> dict[str, object]:
    logger = _get_task_logger()
    require_manifest = exit_code == 0
    manifest, manifest_path, artifact_dir = _load_engine_artifact_manifest(
        local_paths,
        require_manifest=require_manifest,
    )
    if manifest is None or manifest_path is None:
        return {
            "artifact_uris": dict(already_uploaded or {}),
            "engine_manifest_uri": "",
            "mlflow_tags_written": mlflow_tags_written,
        }

    uploaded: dict[str, str] = dict(already_uploaded or {})
    pending_entries = [
        entry
        for entry in manifest.artifacts
        if entry.logical_name not in uploaded
    ]
    if pending_entries:
        gateway = storage_base_url()
        payload = {
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "entries": [
                {
                    "flow_run_id": flow_run_id,
                    "attempt": attempt,
                    "kind": "custom",
                    "filename": f"engine/{entry.relative_path}",
                }
                for entry in pending_entries
            ],
        }
        rows = http_json("POST", f"{gateway}/v1/presign/batch", payload)
        assert isinstance(rows, list)
        if len(rows) != len(pending_entries):
            raise RuntimeError("unexpected presign batch response for engine artifacts")
        for entry, row in zip(pending_entries, rows, strict=True):
            src = _resolve_engine_artifact_path(artifact_dir, entry)
            object_uri = str(row["object_uri"])
            put_url = str(row["url"])
            logger.info(
                "uploading engine artifact: logical_name=%s relative_path=%s object_uri=%s url=%s local_path=%s",
                entry.logical_name,
                entry.relative_path,
                object_uri,
                put_url,
                src,
            )
            upload_file(put_url, src.read_bytes())
            uploaded[entry.logical_name] = object_uri

    engine_manifest_payload = {
        "schema_version": manifest.schema_version,
        "flow_run_id": flow_run_id,
        "attempt": attempt,
        "artifacts": [
            {
                "logical_name": entry.logical_name,
                "relative_path": entry.relative_path,
                "content_type": entry.content_type,
                "description": entry.description,
                "mlflow_tag": entry.mlflow_tag,
                "object_uri": uploaded[entry.logical_name],
            }
            for entry in manifest.artifacts
        ],
    }
    gateway = storage_base_url()
    manifest_link = cast(
        dict[str, object],
        http_json(
            "POST",
            f"{gateway}/v1/presign/put",
            {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "kind": "custom",
                "filename": "engine-artifacts.json",
            },
        ),
    )
    logger.info(
        "uploading engine manifest artifact: object_uri=%s url=%s",
        manifest_link["object_uri"],
        manifest_link["url"],
    )
    upload_file(
        str(manifest_link["url"]),
        json.dumps(engine_manifest_payload, ensure_ascii=True, indent=2).encode("utf-8"),
    )
    engine_manifest_uri = str(manifest_link["object_uri"])

    if not mlflow_tags_written:
        run_id = _extract_run_id_from_stdout(Path(local_paths["stdout"]))
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
        if run_id and tracking_uri:
            _set_mlflow_tag(run_id, "artifact_engine_manifest_uri", engine_manifest_uri)
            for entry in manifest.artifacts:
                if entry.mlflow_tag:
                    _set_mlflow_tag(
                        run_id, entry.mlflow_tag, uploaded[entry.logical_name]
                    )
            mlflow_tags_written = True

    return {
        "artifact_uris": uploaded,
        "engine_manifest_uri": engine_manifest_uri,
        "mlflow_tags_written": mlflow_tags_written,
    }
