from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from prefect import flow
from prefect.context import get_run_context
from prefect.runtime import flow_run

from flows.checkpoint_store import load_checkpoint, resolve_checkpoint_path, save_checkpoint
from flows.engine_run.tasks import prepare_manifest_task, resolve_commit_task, run_entrypoint_task, upload_outputs_task
from runner.git_runner import cleanup_workdir


def _step_done(state: dict[str, Any], step: str) -> bool:
    return bool(state.get("steps", {}).get(step))


def _mark_step(state: dict[str, Any], step: str) -> None:
    state.setdefault("steps", {})[step] = True


def _artifact_paths_exist(local_paths: dict[str, str]) -> bool:
    return all(Path(local_paths[k]).exists() for k in ("stdout", "stderr", "result"))


@flow(name="engine-run", retries=3, retry_delay_seconds=30)
def engine_run_flow(
    repo_url: str,
    ref: str,
    entrypoint: list[str],
    inputs_ref: list[str] | None = None,
    env: dict[str, str] | None = None,
    outputs_prefix: str | None = None,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, object]:
    _ = (inputs_ref, outputs_prefix)
    run_id = flow_run.get_id()
    active_resume_key = resume_key or run_id
    checkpoint_path = resolve_checkpoint_path(
        checkpoint_dir=checkpoint_dir or os.getenv("ORCHESTRATOR_CHECKPOINT_DIR"),
        resume_key=active_resume_key,
    )
    state = load_checkpoint(checkpoint_path)
    state.setdefault("flow_run_id", run_id)
    state.setdefault("resume_key", active_resume_key)
    state.setdefault("steps", {})

    try:
        attempt = int(get_run_context().flow_run.run_count or 1)
    except Exception:
        attempt = 1
    state["attempt"] = attempt
    save_checkpoint(checkpoint_path, state)

    if _step_done(state, "resolve_commit"):
        resolved_commit = str(state["resolved_commit"])
    else:
        resolved_commit = resolve_commit_task(repo_url, ref)
        state["resolved_commit"] = resolved_commit
        _mark_step(state, "resolve_commit")
        save_checkpoint(checkpoint_path, state)

    local_paths = state.get("local_paths", {})
    if _step_done(state, "run_entrypoint") and isinstance(local_paths, dict) and not _artifact_paths_exist(local_paths):
        state["steps"]["run_entrypoint"] = False
        for key in ("stdout_uploaded", "stderr_uploaded", "result_uploaded", "manifest_uploaded", "cleanup"):
            state["steps"][key] = False
        state["uploaded"] = {}
        save_checkpoint(checkpoint_path, state)

    if _step_done(state, "run_entrypoint"):
        local_paths = state["local_paths"]
        exit_code = int(state.get("exit_code", 1))
    else:
        local_paths, exit_code = run_entrypoint_task(repo_url, resolved_commit, entrypoint, env or {})
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
        state["links"] = [link.__dict__ for link in links]
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

    return {
        "flow_run_id": run_id,
        "attempt": attempt,
        "resolved_commit": resolved_commit,
        "outputs_prefix": f"jobs/{run_id}/attempt-{attempt}/",
        "stdout_uri": uploaded.get("stdout"),
        "stderr_uri": uploaded.get("stderr"),
        "result_uri": uploaded.get("result"),
        "manifest_uri": uploaded.get("manifest"),
        "exit_code": exit_code,
    }
