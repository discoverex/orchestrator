from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from urllib import request

from flows.engine_run.models import EngineArtifactManifest, EngineArtifactManifestEntry


def load_engine_artifact_manifest(
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


def resolve_engine_artifact_path(
    artifact_dir: Path, entry: EngineArtifactManifestEntry
) -> Path:
    resolved = (artifact_dir / entry.relative_path).resolve()
    if not str(resolved).startswith(str(artifact_dir.resolve()) + os.sep):
        raise RuntimeError(
            f"engine artifact escapes artifact root: {entry.relative_path}"
        )
    if not resolved.exists() or not resolved.is_file():
        raise RuntimeError(f"engine artifact file not found: {entry.relative_path}")
    return resolved


def mlflow_headers() -> dict[str, str]:
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


def mlflow_post(path: str, payload: dict[str, object]) -> dict[str, Any]:
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip().rstrip("/")
    if not tracking_uri:
        raise RuntimeError("missing required environment variable: MLFLOW_TRACKING_URI")
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        f"{tracking_uri}{path}",
        method="POST",
        data=body,
        headers=mlflow_headers(),
    )
    with request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError("unexpected MLflow response type")
    return cast(dict[str, Any], parsed)


def set_mlflow_tag(
    run_id: str,
    key: str,
    value: str,
    *,
    mlflow_post_fn: Callable[[str, dict[str, object]], dict[str, Any]],
) -> None:
    mlflow_post_fn(
        "/api/2.0/mlflow/runs/set-tag",
        {"run_id": run_id, "key": key, "value": value},
    )


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
