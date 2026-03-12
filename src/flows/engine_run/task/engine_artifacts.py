from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict, cast

from flows.engine_run.task.support import (
    extract_run_id_from_stdout,
    load_engine_artifact_manifest,
    resolve_engine_artifact_path,
    set_mlflow_tag,
)


class EngineArtifactsUploadResult(TypedDict):
    artifact_uris: dict[str, str]
    engine_manifest_uri: str
    mlflow_tags_written: bool


def upload_engine_artifacts(
    local_paths: dict[str, str],
    flow_run_id: str,
    attempt: int,
    exit_code: int,
    *,
    logger: logging.Logger,
    http_json_fn: Callable[[str, str, dict[str, object]], object],
    storage_base_url_fn: Callable[[], str],
    upload_file_fn: Callable[[str, bytes], None],
    mlflow_post_fn: Callable[[str, dict[str, object]], dict[str, Any]],
    already_uploaded: dict[str, str] | None = None,
    mlflow_tags_written: bool = False,
) -> EngineArtifactsUploadResult:
    manifest, manifest_path, artifact_dir = load_engine_artifact_manifest(
        local_paths,
        require_manifest=exit_code == 0,
    )
    if manifest is None or manifest_path is None:
        return {
            "artifact_uris": dict(already_uploaded or {}),
            "engine_manifest_uri": "",
            "mlflow_tags_written": mlflow_tags_written,
        }

    uploaded: dict[str, str] = dict(already_uploaded or {})
    pending_entries = [
        entry for entry in manifest.artifacts if entry.logical_name not in uploaded
    ]
    if pending_entries:
        gateway = storage_base_url_fn()
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
        rows = http_json_fn("POST", f"{gateway}/v1/presign/batch", payload)
        assert isinstance(rows, list)
        if len(rows) != len(pending_entries):
            raise RuntimeError("unexpected presign batch response for engine artifacts")
        for entry, row in zip(pending_entries, rows, strict=True):
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
            upload_file_fn(put_url, src.read_bytes())
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
    gateway = storage_base_url_fn()
    manifest_link = cast(
        dict[str, object],
        http_json_fn(
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
    upload_file_fn(
        str(manifest_link["url"]),
        json.dumps(engine_manifest_payload, ensure_ascii=True, indent=2).encode(
            "utf-8"
        ),
    )
    engine_manifest_uri = str(manifest_link["object_uri"])

    if not mlflow_tags_written:
        run_id = extract_run_id_from_stdout(Path(local_paths["stdout"]))
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
        if run_id and tracking_uri:
            set_mlflow_tag(
                run_id,
                "artifact_engine_manifest_uri",
                engine_manifest_uri,
                mlflow_post_fn=mlflow_post_fn,
            )
            for entry in manifest.artifacts:
                if entry.mlflow_tag:
                    set_mlflow_tag(
                        run_id,
                        entry.mlflow_tag,
                        uploaded[entry.logical_name],
                        mlflow_post_fn=mlflow_post_fn,
                    )
            mlflow_tags_written = True

    return {
        "artifact_uris": uploaded,
        "engine_manifest_uri": engine_manifest_uri,
        "mlflow_tags_written": mlflow_tags_written,
    }
