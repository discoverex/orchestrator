from __future__ import annotations

from pathlib import Path
from typing import Any


def step_done(state: dict[str, Any], step: str) -> bool:
    return bool(state.get("steps", {}).get(step))


def mark_step(state: dict[str, Any], step: str) -> None:
    state.setdefault("steps", {})[step] = True


def artifact_paths_exist(local_paths: dict[str, str]) -> bool:
    return all(Path(local_paths[k]).exists() for k in ("stdout", "stderr", "result"))
