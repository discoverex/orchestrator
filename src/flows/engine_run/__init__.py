from __future__ import annotations

from importlib import import_module
from typing import Any

from flows.engine_run.models import ArtifactLink
from flows.engine_run.task.main import upload_outputs_task

__all__ = ["ArtifactLink", "engine_run_flow", "run_job_flow", "upload_outputs_task"]


def __getattr__(name: str) -> Any:
    if name in {"engine_run_flow", "run_job_flow"}:
        module = import_module("flows.engine_run.flow")
        return getattr(module, name)
    raise AttributeError(f"module 'flows.engine_run' has no attribute {name!r}")
