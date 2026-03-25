from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


class JobSpecError(RuntimeError):
    pass


@dataclass(frozen=True)
class JobSpec:
    engine: str
    entrypoint: list[str]
    run_mode: Literal["repo", "inline"] = "repo"
    repo_url: str | None = None
    ref: str | None = None
    config: str | None = None
    job_name: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    outputs_prefix: str | None = None

    def __post_init__(self) -> None:
        self._validate_fields()
        self._validate_repo_fields_for_mode()

    def _validate_fields(self) -> None:
        if not self.engine.strip():
            raise JobSpecError("engine must not be blank")

        if self.repo_url is not None and not self.repo_url.strip():
            raise JobSpecError("repo_url must not be blank when provided")

        if self.ref is not None and not self.ref.strip():
            raise JobSpecError("ref must not be blank when provided")

        if not self.entrypoint:
            raise JobSpecError("entrypoint must not be empty")

        if any(not str(item).strip() for item in self.entrypoint):
            raise JobSpecError("entrypoint items must not be blank")

        if self.config is not None:
            raw = self.config.strip()
            if not raw:
                raise JobSpecError("config must not be blank when provided")
            p = Path(raw)
            if p.is_absolute():
                raise JobSpecError("config must be a repository-relative path")
            if ".." in p.parts:
                raise JobSpecError("config must not escape repository root")

        if self.job_name is not None and not self.job_name.strip():
            raise JobSpecError("job_name must not be blank when provided")

    def _validate_repo_fields_for_mode(self) -> None:
        if self.run_mode == "inline":
            if self.repo_url is not None:
                raise JobSpecError("repo_url must be omitted when run_mode=inline")
            if self.ref is not None:
                raise JobSpecError("ref must be omitted when run_mode=inline")
            if self.config is not None:
                raise JobSpecError("config must be omitted when run_mode=inline")
        elif self.run_mode == "repo":
            if not self.repo_url:
                raise JobSpecError("repo_url is required when run_mode=repo")
            if not self.ref:
                raise JobSpecError("ref is required when run_mode=repo")
