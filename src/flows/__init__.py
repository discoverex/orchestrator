from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "engine_run_flow",
    "run_job_flow",
    "run_worker_job_flow",
    "worker_runtime_flow",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        module = import_module("flows.worker_runtime.flow")
        if name == "engine_run_flow":
            return module.worker_runtime_flow
        if name == "run_job_flow":
            return module.run_worker_job_flow
        if name == "run_worker_job_flow":
            return module.run_worker_job_flow
        return module.worker_runtime_flow
    raise AttributeError(f"module 'flows' has no attribute {name!r}")
