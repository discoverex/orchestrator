from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any, TypeVar

from pydantic import TypeAdapter

_SAFE_KEY = re.compile(r"[^a-zA-Z0-9._-]+")

T = TypeVar("T")


def sanitize_resume_key(value: str) -> str:
    cleaned = _SAFE_KEY.sub("-", value.strip())
    cleaned = cleaned.strip("-")
    return cleaned or "run"


def resolve_checkpoint_path(checkpoint_dir: str | None, resume_key: str) -> Path | None:
    if not checkpoint_dir:
        return None
    base = Path(checkpoint_dir).expanduser()
    if not base.exists():
        raise RuntimeError(f"checkpoint_dir does not exist: {base}")
    if not base.is_dir():
        raise RuntimeError(f"checkpoint_dir is not a directory: {base}")
    return base / f"{sanitize_resume_key(resume_key)}.json"


def load_checkpoint(path: Path | None, model_cls: type[T]) -> T | None:
    if path is None or not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        adapter = TypeAdapter(model_cls)
        return adapter.validate_json(raw)
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def save_checkpoint(path: Path | None, state: Any) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")

    if dataclasses.is_dataclass(state):
        # Use TypeAdapter to handle potential Pydantic-friendly types if any nested
        adapter = TypeAdapter(type(state))
        payload = adapter.dump_json(state, indent=2).decode("utf-8")
    elif hasattr(state, "model_dump_json"):
        payload = state.model_dump_json(indent=2)
    else:
        payload = json.dumps(state, indent=2)

    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)
