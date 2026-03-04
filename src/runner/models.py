from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodeRef:
    repo_url: str
    ref: str
    resolved_commit: str
    entrypoint: list[str]


@dataclass(frozen=True)
class RunArtifacts:
    workdir: Path
    stdout_path: Path
    stderr_path: Path
    result_path: Path
    exit_code: int
