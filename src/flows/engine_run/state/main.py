from __future__ import annotations

from pathlib import Path

from flows.engine_run.models import FlowResult


def artifact_paths_exist(local_paths: dict[str, str]) -> bool:
    return all(Path(local_paths[k]).exists() for k in ("stdout", "stderr", "result"))


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
    engine_manifest_uri: str | None,
    engine_uploaded: dict[str, str],
    exit_code: int,
) -> FlowResult:
    return FlowResult(
        flow_run_id=flow_run_id,
        attempt=attempt,
        engine=engine,
        run_mode=run_mode,
        job_name=job_name,
        resolved_commit=resolved_commit,
        outputs_prefix=outputs_prefix,
        stdout_uri=uploaded.get("stdout"),
        stderr_uri=uploaded.get("stderr"),
        result_uri=uploaded.get("result"),
        manifest_uri=uploaded.get("manifest"),
        engine_manifest_uri=engine_manifest_uri or None,
        engine_artifact_uris=engine_uploaded,
        exit_code=exit_code,
    )
