from __future__ import annotations

from pathlib import PurePosixPath

from pydantic import Field, field_validator

from common import StrictModel


class ArtifactLink(StrictModel):
    kind: str
    object_uri: str
    url: str


class FlowState(StrictModel):
    flow_run_id: str
    resume_key: str
    attempt: int = 1
    resolved_commit: str | None = None
    local_paths: dict[str, str] = Field(default_factory=dict)
    exit_code: int | None = None
    uploaded: dict[str, str] = Field(default_factory=dict)
    engine_uploaded: dict[str, str] = Field(default_factory=dict)
    engine_manifest_uri: str | None = None
    steps: dict[str, bool] = Field(default_factory=dict)
    links: list[ArtifactLink] = Field(default_factory=list)

    def is_step_done(self, step: str) -> bool:
        return self.steps.get(step, False)

    def mark_step(self, step: str) -> FlowState:
        new_steps = dict(self.steps)
        new_steps[step] = True
        return self.model_copy(update={"steps": new_steps})

    def reset_after_missing_artifacts(self) -> FlowState:
        new_steps = dict(self.steps)
        new_steps["run_entrypoint"] = False
        for key in (
            "stdout_uploaded",
            "stderr_uploaded",
            "result_uploaded",
            "manifest_uploaded",
            "engine_artifacts_uploaded",
            "engine_manifest_uploaded",
            "engine_mlflow_tags_written",
            "cleanup",
        ):
            new_steps[key] = False
        return self.model_copy(
            update={
                "steps": new_steps,
                "uploaded": {},
                "engine_uploaded": {},
                "engine_manifest_uri": None,
            }
        )


class FlowResult(StrictModel):
    flow_run_id: str
    attempt: int
    engine: str
    run_mode: str
    job_name: str | None = None
    resolved_commit: str
    outputs_prefix: str
    stdout_uri: str | None = None
    stderr_uri: str | None = None
    result_uri: str | None = None
    manifest_uri: str | None = None
    engine_manifest_uri: str | None = None
    engine_artifact_uris: dict[str, str] = Field(default_factory=dict)
    exit_code: int


class EngineArtifactsUploadResult(StrictModel):
    artifact_uris: dict[str, str] = Field(default_factory=dict)
    engine_manifest_uri: str = ""
    mlflow_tags_written: bool = False


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
