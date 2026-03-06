from __future__ import annotations

from pathlib import Path

import pytest

from flows.checkpoint_store import (
    load_checkpoint,
    resolve_checkpoint_path,
    sanitize_resume_key,
    save_checkpoint,
)


def test_sanitize_resume_key() -> None:
    assert sanitize_resume_key(" flow/run 01 ") == "flow-run-01"
    assert sanitize_resume_key("///") == "run"


def test_load_and_save_checkpoint_roundtrip(tmp_path: Path) -> None:
    path = resolve_checkpoint_path(str(tmp_path), "flow/1")
    assert path is not None
    payload = {"steps": {"resolve_commit": True}, "attempt": 1}
    save_checkpoint(path, payload)
    assert load_checkpoint(path) == payload


def test_resolve_checkpoint_path_requires_existing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "missing-dir"
    with pytest.raises(RuntimeError):
        resolve_checkpoint_path(str(missing), "flow")
