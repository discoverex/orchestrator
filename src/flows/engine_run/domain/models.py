from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ArtifactLink:
    kind: str
    object_uri: str
    url: str


@dataclass(frozen=True)
class FlowState:
    flow_run_id: str
    resume_key: str
    attempt: int = 1
    resolved_commit: str | None = None
    local_paths: dict[str, str] = field(default_factory=dict)
    exit_code: int | None = None
    uploaded: dict[str, str] = field(default_factory=dict)
    engine_uploaded: dict[str, str] = field(default_factory=dict)
    engine_manifest_uri: str | None = None
    steps: dict[str, bool] = field(default_factory=dict)
    links: list[ArtifactLink] = field(default_factory=list)

    def is_step_done(self, step: str) -> bool:
        return self.steps.get(step, False)

    def mark_step(self, step: str) -> FlowState:
        new_steps = dict(self.steps)
        new_steps[step] = True
        return dataclasses.replace(self, steps=new_steps)

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
        return dataclasses.replace(
            self,
            steps=new_steps,
            uploaded={},
            engine_uploaded={},
            engine_manifest_uri=None,
        )


@dataclass(frozen=True)
class FlowResult:
    flow_run_id: str
    attempt: int
    engine: str
    run_mode: str
    resolved_commit: str
    outputs_prefix: str
    exit_code: int
    job_name: str | None = None
    stdout_uri: str | None = None
    stderr_uri: str | None = None
    result_uri: str | None = None
    manifest_uri: str | None = None
    engine_manifest_uri: str | None = None
    engine_artifact_uris: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineArtifactsUploadResult:
    artifact_uris: dict[str, str] = field(default_factory=dict)
    engine_manifest_uri: str = ""
    mlflow_tags_written: bool = False
