from __future__ import annotations

from pathlib import PurePosixPath

from pydantic import Field, field_validator

from common.schema import StrictModel


class EngineArtifactManifestEntry(StrictModel):
    logical_name: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    content_type: str | None = None
    mlflow_tag: str | None = None
    description: str | None = None

    @field_validator("logical_name", "relative_path", "content_type", "mlflow_tag")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank when provided")
        return trimmed

    @field_validator("relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute():
            raise ValueError("relative_path must not be absolute")
        if ".." in path.parts:
            raise ValueError("relative_path must not escape artifact root")
        return value


class EngineArtifactManifest(StrictModel):
    schema_version: int
    artifacts: list[EngineArtifactManifestEntry] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("schema_version must be 1")
        return value

    @field_validator("artifacts")
    @classmethod
    def _validate_unique_fields(
        cls, value: list[EngineArtifactManifestEntry]
    ) -> list[EngineArtifactManifestEntry]:
        logical_names = set()
        relative_paths = set()
        for item in value:
            if item.logical_name in logical_names:
                raise ValueError(
                    f"duplicate engine artifact logical_name: {item.logical_name}"
                )
            logical_names.add(item.logical_name)
            if item.relative_path in relative_paths:
                raise ValueError(
                    f"duplicate engine artifact relative_path: {item.relative_path}"
                )
            relative_paths.add(item.relative_path)
        return value
