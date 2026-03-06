from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from common import StrictModel
from pydantic import Field, ValidationError, field_validator


class JobSpecError(RuntimeError):
    pass


class JobSpec(StrictModel):
    engine: str = Field(min_length=1)
    repo_url: str = Field(min_length=1)
    ref: str = Field(min_length=1)
    entrypoint: list[str]
    config: str | None = None
    job_name: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    outputs_prefix: str | None = None

    @field_validator("engine", "repo_url", "ref")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed

    @field_validator("entrypoint")
    @classmethod
    def _validate_entrypoint(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("entrypoint must not be empty")
        normalized = [str(item) for item in value]
        if any(not item.strip() for item in normalized):
            raise ValueError("entrypoint items must not be blank")
        return normalized

    @field_validator("config")
    @classmethod
    def _validate_config_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        raw = value.strip()
        if not raw:
            raise ValueError("config must not be blank when provided")
        p = Path(raw)
        if p.is_absolute():
            raise ValueError("config must be a repository-relative path")
        if ".." in p.parts:
            raise ValueError("config must not escape repository root")
        return raw

    @field_validator("job_name")
    @classmethod
    def _validate_job_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("job_name must not be blank when provided")
        return trimmed


def _load_registry(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    engines = payload.get("engines")
    if isinstance(engines, list):
        return {str(item) for item in engines if str(item).strip()}
    if isinstance(engines, dict):
        return {str(item) for item in engines.keys() if str(item).strip()}
    raise JobSpecError(f"invalid engine registry shape in {path}")


def validate_engine_registry(engine: str) -> None:
    registry_path = Path(os.getenv("ORCH_ENGINE_REGISTRY_PATH", "infra/engines/registry.json"))
    if not registry_path.exists():
        return
    allowed = _load_registry(registry_path)
    if engine not in allowed:
        raise JobSpecError(f"engine not in registry: {engine}")


def parse_job_spec_json(raw: str) -> JobSpec:
    try:
        spec = JobSpec.model_validate_json(raw)
    except ValidationError as exc:
        raise JobSpecError(f"invalid job spec: {exc}") from exc
    validate_engine_registry(spec.engine)
    return spec
