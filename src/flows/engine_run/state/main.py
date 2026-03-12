from __future__ import annotations

from pathlib import Path
from typing import Any


def step_done(state: dict[str, Any], step: str) -> bool:
    return bool(state.get("steps", {}).get(step))


def mark_step(state: dict[str, Any], step: str) -> None:
    state.setdefault("steps", {})[step] = True


def artifact_paths_exist(local_paths: dict[str, str]) -> bool:
    return all(Path(local_paths[k]).exists() for k in ("stdout", "stderr", "result"))


def reset_after_missing_artifacts(state: dict[str, Any]) -> None:
    state["steps"]["run_entrypoint"] = False
    for key in (
        "stdout_uploaded",
        "stderr_uploaded",
        "result_uploaded",
        "manifest_uploaded",
        "engine_artifacts_uploaded",
        "engine_manifest_uploaded",
        "engine_mlflow_tags_written",
        "cleanup",
    ):
        state["steps"][key] = False
    state["uploaded"] = {}
    state["engine_uploaded"] = {}
    state["engine_manifest_uri"] = ""


def build_flow_result(
    *,
    flow_run_id: str,
    attempt: int,
    engine: str,
    run_mode: str,
    job_name: str | None,
    resolved_commit: str,
    outputs_prefix: str,
    uploaded: dict[str, str],
    engine_manifest_uri: str,
    engine_uploaded: dict[str, str],
    exit_code: int,
) -> dict[str, object]:
    return {
        "flow_run_id": flow_run_id,
        "attempt": attempt,
        "engine": engine,
        "run_mode": run_mode,
        "job_name": job_name,
        "resolved_commit": resolved_commit,
        "outputs_prefix": outputs_prefix,
        "stdout_uri": uploaded.get("stdout"),
        "stderr_uri": uploaded.get("stderr"),
        "result_uri": uploaded.get("result"),
        "manifest_uri": uploaded.get("manifest"),
        "engine_manifest_uri": engine_manifest_uri or None,
        "engine_artifact_uris": engine_uploaded,
        "exit_code": exit_code,
    }
