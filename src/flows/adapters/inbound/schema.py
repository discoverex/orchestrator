from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from flows.domain.run_request import RunRequest, RunRequestError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunRequestSchema(StrictModel):
    run_mode: Literal["repo", "inline"] = "repo"
    engine: str = Field(min_length=1)
    repo_url: str | None = None
    ref: str | None = None
    flow_entrypoint: str
    config: str | None = None
    job_name: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    outputs_prefix: str | None = None

    @field_validator("engine")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed

    @field_validator("repo_url", "ref")
    @classmethod
    def _strip_optional_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank when provided")
        return trimmed

    @field_validator("flow_entrypoint")
    @classmethod
    def _validate_flow_entrypoint(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("flow_entrypoint must not be blank")
        return trimmed

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

    @model_validator(mode="after")
    def _validate_repo_fields_for_mode(self) -> RunRequestSchema:
        if self.run_mode == "inline":
            if self.repo_url is not None:
                raise ValueError("repo_url must be omitted when run_mode=inline")
            if self.ref is not None:
                raise ValueError("ref must be omitted when run_mode=inline")
            if self.config is not None:
                raise ValueError("config must be omitted when run_mode=inline")
            return self
        if not self.repo_url:
            raise ValueError("repo_url is required when run_mode=repo")
        if not self.ref:
            raise ValueError("ref is required when run_mode=repo")
        return self

    def to_domain(self) -> RunRequest:
        return RunRequest(
            run_mode=self.run_mode,
            engine=self.engine,
            flow_entrypoint=self.flow_entrypoint,
            repo_url=self.repo_url,
            ref=self.ref,
            config=self.config,
            job_name=self.job_name,
            inputs=self.inputs,
            env=self.env,
            outputs_prefix=self.outputs_prefix,
        )


def _load_registry(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    engines = payload.get("engines")
    if isinstance(engines, list):
        return {str(item) for item in engines if str(item).strip()}
    if isinstance(engines, dict):
        return {str(item) for item in engines.keys() if str(item).strip()}
    raise RunRequestError(f"invalid engine registry shape in {path}")


def validate_engine_registry(engine: str) -> None:
    registry_path = Path(
        os.getenv("ORCH_ENGINE_REGISTRY_PATH", "infra/engines/registry.json")
    )
    if not registry_path.exists():
        return
    allowed = _load_registry(registry_path)
    if engine not in allowed:
        raise RunRequestError(f"engine not in registry: {engine}")

def load_parameters_json(raw: str) -> RunRequest:
    try:
        request_schema = RunRequestSchema.model_validate_json(raw)
    except ValidationError as exc:
        raise RunRequestError(f"invalid flow parameters: {exc}") from exc

    validate_engine_registry(request_schema.engine)
    return request_schema.to_domain()


def validate_run_request(parameters: dict[str, Any]) -> RunRequest:
    try:
        request_schema = RunRequestSchema.model_validate(parameters)
    except ValidationError as exc:
        raise RunRequestError(f"invalid flow parameters: {exc}") from exc

    validate_engine_registry(request_schema.engine)
    return request_schema.to_domain()
