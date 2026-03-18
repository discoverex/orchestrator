from __future__ import annotations

import logging
from typing import cast

from prefect import get_run_logger


def flow_logger() -> logging.Logger:
    try:
        return cast(logging.Logger, get_run_logger())
    except Exception:
        return logging.getLogger("flows.engine_run.flow")


def log_flow_start(logger: logging.Logger, *, run_id: str, job: object) -> None:
    logger.info(
        "run_job_flow started",
        extra={
            "flow_run_id": run_id,
            "engine": getattr(job, "engine", ""),
            "run_mode": getattr(job, "run_mode", ""),
            "repo_url": getattr(job, "repo_url", "") or "",
            "ref": getattr(job, "ref", "") or "",
            "job_name": getattr(job, "job_name", "") or "",
        },
    )


def log_checkpoint_loaded(
    logger: logging.Logger,
    *,
    run_id: str,
    attempt: int,
    checkpoint_path: str,
    resume_key: str,
) -> None:
    logger.info(
        "checkpoint state loaded",
        extra={
            "flow_run_id": run_id,
            "attempt": attempt,
            "checkpoint_path": checkpoint_path,
            "resume_key": resume_key,
        },
    )


def log_flow_finish(
    logger: logging.Logger,
    *,
    run_id: str,
    attempt: int,
    exit_code: int,
    resolved_commit: str,
) -> None:
    logger.info(
        "run_job_flow finished",
        extra={
            "flow_run_id": run_id,
            "attempt": attempt,
            "exit_code": exit_code,
            "resolved_commit": resolved_commit,
        },
    )
