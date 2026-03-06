from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

_SAFE_KEY = re.compile(r"[^a-zA-Z0-9._-]+")


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


def load_checkpoint(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return cast(dict[str, Any], data)
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_checkpoint(path: Path | None, state: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(
        json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    tmp_path.replace(path)
