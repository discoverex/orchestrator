from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flows.engine_run.models import FlowState


def flow_attempt(get_run_context_fn: Callable[[], Any]) -> int:
    try:
        ctx = get_run_context_fn()
        flow_ctx = getattr(ctx, "flow_run", None)
        run_count = getattr(flow_ctx, "run_count", None)
        return int(run_count or 1)
    except Exception:
        return 1


def load_or_init_state(
    checkpoint_path: Path | None,
    *,
    flow_run_id: str,
    resume_key: str,
    attempt: int,
    load_checkpoint_fn: Callable[[Path | None, type[FlowState]], FlowState | None],
    save_checkpoint_fn: Callable[[Path | None, FlowState], None],
) -> FlowState:
    state = load_checkpoint_fn(checkpoint_path, FlowState)
    if state is None:
        state = FlowState(
            flow_run_id=flow_run_id,
            resume_key=resume_key,
            attempt=attempt,
        )
    else:
        state = dataclasses.replace(state, attempt=attempt)
    save_checkpoint_fn(checkpoint_path, state)
    return state


def resolve_commit_for_job(
    *,
    job: Any,
    state: FlowState,
    checkpoint_path: Path | None,
    resolve_commit_task: Callable[[str, str], str],
    logger: Any,
    run_id: str,
    save_checkpoint_fn: Callable[[Path | None, FlowState], None],
) -> tuple[str, FlowState]:
    if job.run_mode == "inline":
        resolved_commit = "inline"
    elif state.is_step_done("resolve_commit"):
        return str(state.resolved_commit), state
    else:
        if not job.repo_url or not job.ref:
            raise RuntimeError("repo_url/ref required for run_mode=repo")
        resolved_commit = resolve_commit_task(job.repo_url, job.ref)
        logger.info(
            "resolved commit for job",
            extra={
                "flow_run_id": run_id,
                "repo_url": job.repo_url,
                "ref": job.ref,
                "resolved_commit": resolved_commit,
            },
        )

    state = dataclasses.replace(state, resolved_commit=resolved_commit)
    state = state.mark_step("resolve_commit")
    save_checkpoint_fn(checkpoint_path, state)
    return resolved_commit, state


def record_entrypoint_state(
    *,
    logger: Any,
    state: FlowState,
    checkpoint_path: Path | None,
    flow_run_id: str,
    attempt: int,
    local_paths: dict[str, str],
    exit_code: int,
    save_checkpoint_fn: Callable[[Path | None, FlowState], None],
) -> FlowState:
    logger.info(
        "entrypoint execution finished",
        extra={
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "exit_code": exit_code,
            "workdir": local_paths.get("workdir", ""),
        },
    )
    state = dataclasses.replace(state, local_paths=local_paths, exit_code=exit_code)
    state = state.mark_step("run_entrypoint")
    steps = dict(state.steps)
    steps["cleanup"] = False
    state = dataclasses.replace(state, steps=steps)
    save_checkpoint_fn(checkpoint_path, state)
    return state


def prepare_flow_state(
    *,
    checkpoint_path: Path | None,
    flow_run_id: str,
    resume_key: str,
    attempt: int,
    job: Any,
    logger: Any,
    resolve_commit_task: Callable[[str, str], str],
    load_checkpoint_fn: Callable[[Path | None, type[FlowState]], FlowState | None],
    save_checkpoint_fn: Callable[[Path | None, FlowState], None],
    log_checkpoint_loaded_fn: Callable[..., None],
) -> tuple[int, FlowState, str]:
    state = load_or_init_state(
        checkpoint_path,
        flow_run_id=flow_run_id,
        resume_key=resume_key,
        attempt=attempt,
        load_checkpoint_fn=load_checkpoint_fn,
        save_checkpoint_fn=save_checkpoint_fn,
    )
    log_checkpoint_loaded_fn(
        logger,
        run_id=flow_run_id,
        attempt=attempt,
        checkpoint_path=str(checkpoint_path),
        resume_key=resume_key,
    )
    resolved_commit, state = resolve_commit_for_job(
        job=job,
        state=state,
        checkpoint_path=checkpoint_path,
        resolve_commit_task=resolve_commit_task,
        logger=logger,
        run_id=flow_run_id,
        save_checkpoint_fn=save_checkpoint_fn,
    )
    return attempt, state, resolved_commit
