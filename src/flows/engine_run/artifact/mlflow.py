from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from flows.engine_run.models import EngineArtifactManifest


def maybe_write_mlflow_tags(
    *,
    local_paths: dict[str, str],
    tracking_uri: str,
    manifest: EngineArtifactManifest,
    uploaded: dict[str, str],
    engine_manifest_uri: str,
    set_mlflow_tag: Callable[[str, str, str], None],
) -> bool:
    run_id = extract_run_id_from_stdout(Path(local_paths["stdout"]))
    if not run_id or not tracking_uri:
        return False
    set_mlflow_tag(run_id, "artifact_engine_manifest_uri", engine_manifest_uri)
    for entry in manifest.artifacts:
        if entry.mlflow_tag:
            set_mlflow_tag(run_id, entry.mlflow_tag, uploaded[entry.logical_name])
    return True


def extract_run_id_from_stdout(stdout_path: Path) -> str:
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
