from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from prefect import flow
from prefect.context import get_run_context
from prefect.runtime import flow_run

from flows.checkpoint_store import (
    load_checkpoint,
    resolve_checkpoint_path,
    save_checkpoint,
)
from flows.engine_run.tasks import (
    prepare_manifest_task,
    resolve_commit_task,
    run_entrypoint_job_task,
    upload_outputs_task,
)
from flows.job_spec import parse_job_spec_json
from runner.git_runner import cleanup_workdir


def _step_done(state: dict[str, Any], step: str) -> bool:
    return bool(state.get("steps", {}).get(step))


def _mark_step(state: dict[str, Any], step: str) -> None:
    state.setdefault("steps", {})[step] = True


def _artifact_paths_exist(local_paths: dict[str, str]) -> bool:
    return all(Path(local_paths[k]).exists() for k in ("stdout", "stderr", "result"))


def _flow_attempt() -> int:
    try:
        ctx = get_run_context()
        flow_ctx = getattr(ctx, "flow_run", None)
        run_count = getattr(flow_ctx, "run_count", None)
        return int(run_count or 1)
    except Exception:
        return 1


@flow(name="run-job", retries=3, retry_delay_seconds=30)
def run_job_flow(
    job_spec_json: str | dict[str, Any],
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, object]:
    run_id = flow_run.get_id() or "unknown-flow-run"
    if isinstance(job_spec_json, dict):
        import json

        job_spec_raw = json.dumps(job_spec_json, ensure_ascii=True)
    else:
        job_spec_raw = job_spec_json
    job = parse_job_spec_json(job_spec_raw)
    active_resume_key = resume_key or run_id
    checkpoint_path = resolve_checkpoint_path(
        checkpoint_dir=checkpoint_dir or os.getenv("ORCHESTRATOR_CHECKPOINT_DIR"),
        resume_key=active_resume_key,
    )
    state = load_checkpoint(checkpoint_path)
    state.setdefault("flow_run_id", run_id)
    state.setdefault("resume_key", active_resume_key)
    state.setdefault("steps", {})

    attempt = _flow_attempt()
    state["attempt"] = attempt
    save_checkpoint(checkpoint_path, state)

    if job.run_mode == "inline":
        resolved_commit = "inline"
        state["resolved_commit"] = resolved_commit
        _mark_step(state, "resolve_commit")
        save_checkpoint(checkpoint_path, state)
    elif _step_done(state, "resolve_commit"):
        resolved_commit = str(state["resolved_commit"])
    else:
        if not job.repo_url or not job.ref:
            raise RuntimeError("repo_url/ref required for run_mode=repo")
        resolved_commit = resolve_commit_task(job.repo_url, job.ref)
        state["resolved_commit"] = resolved_commit
        _mark_step(state, "resolve_commit")
        save_checkpoint(checkpoint_path, state)

    local_paths = state.get("local_paths", {})
    if (
        _step_done(state, "run_entrypoint")
        and isinstance(local_paths, dict)
        and not _artifact_paths_exist(local_paths)
    ):
        state["steps"]["run_entrypoint"] = False
        for key in (
            "stdout_uploaded",
            "stderr_uploaded",
            "result_uploaded",
            "manifest_uploaded",
            "cleanup",
        ):
            state["steps"][key] = False
        state["uploaded"] = {}
        save_checkpoint(checkpoint_path, state)

    if _step_done(state, "run_entrypoint"):
        local_paths = cast(dict[str, str], state["local_paths"])
        exit_code = int(state.get("exit_code", 1))
    else:
        effective_outputs_prefix = (
            job.outputs_prefix or f"jobs/{run_id}/attempt-{attempt}/"
        )
        local_paths, exit_code = run_entrypoint_job_task(
            repo_url=job.repo_url,
            resolved_commit=resolved_commit,
            entrypoint=job.entrypoint,
            env=job.env,
            run_mode=job.run_mode,
            engine=job.engine,
            config_rel_path=job.config,
            inputs=job.inputs,
            flow_run_id=run_id,
            attempt=attempt,
            outputs_prefix=effective_outputs_prefix,
            job_name=job.job_name,
        )
        state["local_paths"] = local_paths
        state["exit_code"] = exit_code
        _mark_step(state, "run_entrypoint")
        state["steps"]["cleanup"] = False
        save_checkpoint(checkpoint_path, state)

    if _step_done(state, "manifest_uploaded"):
        uploaded = dict(state.get("uploaded", {}))
    else:
        links = prepare_manifest_task(run_id, attempt)
        _mark_step(state, "prepare_manifest")
        state["links"] = [link.model_dump(mode="json") for link in links]
        save_checkpoint(checkpoint_path, state)

        uploaded = upload_outputs_task(
            links,
            local_paths,
            run_id,
            attempt,
            already_uploaded=state.get("uploaded", {}),
        )
        state["uploaded"] = uploaded
        for key in ("stdout", "stderr", "result", "manifest"):
            if key in uploaded:
                _mark_step(state, f"{key}_uploaded")
        save_checkpoint(checkpoint_path, state)

    workdir = Path(local_paths["workdir"])
    if not _step_done(state, "cleanup") and workdir.exists():
        cleanup_workdir(workdir)
        _mark_step(state, "cleanup")
        save_checkpoint(checkpoint_path, state)

    effective_outputs_prefix = job.outputs_prefix or f"jobs/{run_id}/attempt-{attempt}/"
    return {
        "flow_run_id": run_id,
        "attempt": attempt,
        "engine": job.engine,
        "run_mode": job.run_mode,
        "job_name": job.job_name,
        "resolved_commit": resolved_commit,
        "outputs_prefix": effective_outputs_prefix,
        "stdout_uri": uploaded.get("stdout"),
        "stderr_uri": uploaded.get("stderr"),
        "result_uri": uploaded.get("result"),
        "manifest_uri": uploaded.get("manifest"),
        "exit_code": exit_code,
    }


engine_run_flow = run_job_flow
