from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from runner.adapters.outbound.git.runner import cleanup_workdir, run_entrypoint

FIXTURE_REPO = Path(__file__).resolve().parents[1] / "fixtures" / "dummy_engine_repo"


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(["git", *cmd], cwd=cwd, check=True, capture_output=True, text=True)


def _create_engine_repo(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    shutil.copytree(FIXTURE_REPO, source)
    (source / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "dummy-engine-repo"',
                'version = "0.1.0"',
                'requires-python = ">=3.11"',
            ]
        ),
        encoding="utf-8",
    )
    _git(["init"], cwd=source)
    _git(["config", "user.name", "Test User"], cwd=source)
    _git(["config", "user.email", "test@example.com"], cwd=source)
    _git(["add", "."], cwd=source)
    _git(["commit", "-m", "initial"], cwd=source)
    _git(["branch", "-M", "main"], cwd=source)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return source, commit


def test_run_entrypoint_requires_repo_mode() -> None:
    with pytest.raises(RuntimeError, match="requires run_mode=repo"):
        run_entrypoint(
            repo_url=None,
            ref=None,
            resolved_commit=None,
            flow_entrypoint="src/dummy_engine/prefect_flow.py:dummy_engine_flow",
            run_mode="inline",
            env={},
            engine="dummy-engine",
            config_rel_path=None,
            inputs={},
            flow_run_id="flow-inline",
            attempt=1,
            outputs_prefix="jobs/flow-inline/attempt-1/",
            job_name="inline-smoke",
        )


def test_run_entrypoint_executes_prefect_subflow_from_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "runtime"
    repo_path, commit = _create_engine_repo(tmp_path)
    monkeypatch.setenv("ORCH_WORKER_RUNTIME_DIR", str(runtime_root))

    artifacts = run_entrypoint(
        repo_url=str(repo_path),
        ref="main",
        resolved_commit=commit,
        flow_entrypoint="src/dummy_engine/prefect_flow.py:dummy_engine_flow",
        run_mode="repo",
        env={"MLFLOW_TRACKING_URI": ""},
        engine="dummy-engine",
        config_rel_path=None,
        inputs={"scene_id": "scene-1", "version_id": "ver-1"},
        flow_run_id="flow-repo",
        attempt=1,
        outputs_prefix="jobs/flow-repo/attempt-1/",
        job_name="repo-subflow-check",
    )
    try:
        assert artifacts.exit_code == 0
        result = json.loads(artifacts.result_path.read_text(encoding="utf-8"))
        assert (
            result["flow_entrypoint"]
            == "src/dummy_engine/prefect_flow.py:dummy_engine_flow"
        )
        assert result["result"]["scene_id"] == "scene-1"
        assert result["result"]["version_id"] == "ver-1"

        scene = json.loads(
            (artifacts.engine_artifact_dir / "scene" / "scene.json").read_text(
                encoding="utf-8"
            )
        )
        assert scene["scene_id"] == "scene-1"
        assert scene["version_id"] == "ver-1"

        manifest = json.loads(
            artifacts.engine_artifact_manifest_path.read_text(encoding="utf-8")
        )
        assert manifest["schema_version"] == 1
    finally:
        cleanup_workdir(artifacts.workdir)


def test_run_entrypoint_injects_parent_runtime_dirs_into_subflow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "runtime"
    repo_path, commit = _create_engine_repo(tmp_path)
    monkeypatch.setenv("ORCH_WORKER_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://storage-api.example/mlflow")

    artifacts = run_entrypoint(
        repo_url=str(repo_path),
        ref="main",
        resolved_commit=commit,
        flow_entrypoint="src/dummy_engine/prefect_flow.py:dummy_engine_flow",
        run_mode="repo",
        env={"MLFLOW_TRACKING_URI": ""},
        engine="dummy-engine",
        config_rel_path=None,
        inputs={},
        flow_run_id="flow-runtime-env",
        attempt=1,
        outputs_prefix="jobs/flow-runtime-env/attempt-1/",
        job_name="runtime-env-check",
    )
    try:
        scene = json.loads(
            (artifacts.engine_artifact_dir / "scene" / "scene.json").read_text(
                encoding="utf-8"
            )
        )
        assert scene["flow_run_id"] == "flow-runtime-env"
        result = json.loads(artifacts.result_path.read_text(encoding="utf-8"))
        summary = result["env_summary"]
        assert summary["ORCH_WORKER_RUNTIME_DIR"] == str(runtime_root)
        assert summary["ORCH_CACHE_DIR"] == str(runtime_root / "cache")
        assert "ORCH_REPO_CACHE_DIR" not in summary
    finally:
        cleanup_workdir(artifacts.workdir)
