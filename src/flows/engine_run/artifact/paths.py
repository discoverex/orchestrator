from __future__ import annotations

from pathlib import Path

from flows.engine_run.models import EngineArtifactManifest, EngineArtifactManifestEntry


def load_engine_artifact_manifest(
    local_paths: dict[str, str],
    *,
    require_manifest: bool,
) -> tuple[EngineArtifactManifest | None, Path | None, Path]:
    artifact_dir = Path(local_paths["engine_artifact_dir"])
    manifest_path = Path(local_paths["engine_artifact_manifest"])
    if not manifest_path.exists():
        if require_manifest:
            raise RuntimeError(
                f"successful engine run must write manifest: {manifest_path}"
            )
        return None, None, artifact_dir
    payload = manifest_path.read_text(encoding="utf-8")
    return (
        EngineArtifactManifest.model_validate_json(payload),
        manifest_path,
        artifact_dir,
    )


def resolve_engine_artifact_path(
    artifact_dir: Path,
    entry: EngineArtifactManifestEntry,
) -> Path:
    resolved = (artifact_dir / entry.relative_path).resolve()
    if not str(resolved).startswith(str(artifact_dir.resolve()) + "/"):
        raise RuntimeError(
            f"engine artifact escapes artifact root: {entry.relative_path}"
        )
    if not resolved.exists() or not resolved.is_file():
        raise RuntimeError(f"engine artifact file not found: {entry.relative_path}")
    return resolved
