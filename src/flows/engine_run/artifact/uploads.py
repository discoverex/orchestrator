from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict, cast

from flows.engine_run.artifact.mlflow import maybe_write_mlflow_tags
from flows.engine_run.artifact.paths import (
    load_engine_artifact_manifest,
    resolve_engine_artifact_path,
)
from flows.engine_run.models import EngineArtifactManifest


class EngineArtifactsUploadResult(TypedDict):
    artifact_uris: dict[str, str]
    engine_manifest_uri: str
    mlflow_tags_written: bool


def upload_engine_artifacts(
    *,
    local_paths: dict[str, str],
    flow_run_id: str,
    attempt: int,
    exit_code: int,
    already_uploaded: dict[str, str] | None,
    mlflow_tags_written: bool,
    gateway: str,
    http_json: Callable[[str, str, dict[str, object]], object],
    upload_file: Callable[[str, bytes], None],
    tracking_uri: str,
    set_mlflow_tag: Callable[[str, str, str], None],
    logger: logging.Logger,
) -> EngineArtifactsUploadResult:
    require_manifest = exit_code == 0
    manifest, manifest_path, artifact_dir = load_engine_artifact_manifest(
        local_paths,
        require_manifest=require_manifest,
    )
    if manifest is None or manifest_path is None:
        return {
            "artifact_uris": dict(already_uploaded or {}),
            "engine_manifest_uri": "",
            "mlflow_tags_written": mlflow_tags_written,
        }

    uploaded = _upload_declared_artifacts(
        manifest=manifest,
        artifact_dir=artifact_dir,
        flow_run_id=flow_run_id,
        attempt=attempt,
        already_uploaded=already_uploaded,
        gateway=gateway,
        http_json=http_json,
        upload_file=upload_file,
        logger=logger,
    )
    engine_manifest_uri = _upload_engine_manifest(
        manifest=manifest,
        uploaded=uploaded,
        flow_run_id=flow_run_id,
        attempt=attempt,
        gateway=gateway,
        http_json=http_json,
        upload_file=upload_file,
        logger=logger,
    )
    wrote_tags = mlflow_tags_written or maybe_write_mlflow_tags(
        local_paths=local_paths,
        tracking_uri=tracking_uri,
        manifest=manifest,
        uploaded=uploaded,
        engine_manifest_uri=engine_manifest_uri,
        set_mlflow_tag=set_mlflow_tag,
    )
    return {
        "artifact_uris": uploaded,
        "engine_manifest_uri": engine_manifest_uri,
        "mlflow_tags_written": wrote_tags,
    }


def _upload_declared_artifacts(
    *,
    manifest: EngineArtifactManifest,
    artifact_dir: Path,
    flow_run_id: str,
    attempt: int,
    already_uploaded: dict[str, str] | None,
    gateway: str,
    http_json: Callable[[str, str, dict[str, object]], object],
    upload_file: Callable[[str, bytes], None],
    logger: logging.Logger,
) -> dict[str, str]:
    uploaded: dict[str, str] = dict(already_uploaded or {})
    pending = [
        entry for entry in manifest.artifacts if entry.logical_name not in uploaded
    ]
    if not pending:
        return uploaded

    rows = http_json(
        "POST",
        f"{gateway}/v1/presign/batch",
        {
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "entries": [
                {
                    "flow_run_id": flow_run_id,
                    "attempt": attempt,
                    "kind": "custom",
                    "filename": f"engine/{entry.relative_path}",
                }
                for entry in pending
            ],
        },
    )
    assert isinstance(rows, list)
    if len(rows) != len(pending):
        raise RuntimeError("unexpected presign batch response for engine artifacts")

    for entry, row in zip(pending, rows, strict=True):
        src = resolve_engine_artifact_path(artifact_dir, entry)
        object_uri = str(row["object_uri"])
        put_url = str(row["url"])
        logger.info(
            "uploading engine artifact: "
            "logical_name=%s relative_path=%s object_uri=%s url=%s local_path=%s",
            entry.logical_name,
            entry.relative_path,
            object_uri,
            put_url,
            src,
        )
        upload_file(put_url, src.read_bytes())
        uploaded[entry.logical_name] = object_uri
    return uploaded


def _upload_engine_manifest(
    *,
    manifest: EngineArtifactManifest,
    uploaded: dict[str, str],
    flow_run_id: str,
    attempt: int,
    gateway: str,
    http_json: Callable[[str, str, dict[str, object]], object],
    upload_file: Callable[[str, bytes], None],
    logger: logging.Logger,
) -> str:
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
    payload = {
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
    upload_file(
        str(manifest_link["url"]),
        json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8"),
    )
    return str(manifest_link["object_uri"])
