from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodeRef:
    repo_url: str
    ref: str
    resolved_commit: str
    flow_entrypoint: str


@dataclass(frozen=True)
class RunArtifacts:
    workdir: Path
    stdout_path: Path
    stderr_path: Path
    result_path: Path
    engine_artifact_dir: Path
    engine_artifact_manifest_path: Path
    exit_code: int
