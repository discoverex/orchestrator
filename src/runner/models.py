from __future__ import annotations

from pathlib import Path

from common import StrictModel


class CodeRef(StrictModel):
    repo_url: str
    ref: str
    resolved_commit: str
    entrypoint: list[str]


class RunArtifacts(StrictModel):
    workdir: Path
    stdout_path: Path
    stderr_path: Path
    result_path: Path
    exit_code: int
