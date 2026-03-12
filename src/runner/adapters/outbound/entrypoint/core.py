"""Execution adapter for materializing source and launching engine entrypoints."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import mkdtemp

from runner.adapters.outbound.git.repo import (
    RunnerError,
    checkout_target,
    prepare_cached_repo,
    run_command,
)
from runner.adapters.outbound.mlflow.proxy import maybe_start_mlflow_proxy
from runner.domain.models import RunArtifacts


def prepare_per_repo_venv(workdir: Path, merged_env: dict[str, str]) -> None:
    uv_bin = shutil.which("uv")
    if not uv_bin:
        return

    venv_dir = workdir / ".venv"
    merged_env["UV_PROJECT_ENVIRONMENT"] = str(venv_dir)
    merged_env["PATH"] = f"{venv_dir / 'bin'}:{merged_env.get('PATH', '')}"
    if not (workdir / "pyproject.toml").exists():
        return

    sync_cmd = (
        [uv_bin, "sync", "--frozen"]
        if (workdir / "uv.lock").exists()
        else [uv_bin, "sync"]
    )
    proc = subprocess.run(
        sync_cmd, cwd=workdir, env=merged_env, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RunnerError(
            f"venv setup failed: {' '.join(sync_cmd)}\n{proc.stderr.strip()}"
        )


def run_entrypoint(
    repo_url: str | None,
    ref: str | None,
    resolved_commit: str | None,
    entrypoint: list[str],
    env: dict[str, str] | None = None,
    *,
    run_mode: str = "repo",
    engine: str,
    config_rel_path: str | None,
    inputs: dict[str, object] | None,
    flow_run_id: str,
    attempt: int,
    outputs_prefix: str,
    job_name: str | None = None,
) -> RunArtifacts:
    workdir = Path(mkdtemp(prefix="orchestrator-run-"))
    if run_mode == "repo":
        if not repo_url or not ref or not resolved_commit:
            raise RunnerError(
                "repo_url/ref/resolved_commit are required when run_mode=repo"
            )
        cached_repo = prepare_cached_repo(repo_url, ref, resolved_commit)
        run_command(["git", "clone", "--no-checkout", str(cached_repo), str(workdir)])
        run_command(
            ["git", "checkout", checkout_target(ref, resolved_commit)], cwd=workdir
        )
    elif run_mode == "inline":
        if config_rel_path:
            raise RunnerError("config is not supported when run_mode=inline")
    else:
        raise RunnerError(f"unsupported run_mode: {run_mode}")

    stdout_path = workdir / "stdout.log"
    stderr_path = workdir / "stderr.log"
    result_path = workdir / "result.json"
    engine_artifact_dir = workdir / "engine-artifacts"
    engine_artifact_manifest_path = workdir / "engine-artifacts.manifest.json"
    engine_artifact_dir.mkdir(parents=True, exist_ok=True)

    merged_env = os.environ.copy()
    _apply_runtime_env(
        merged_env=merged_env,
        workdir=workdir,
        config_rel_path=config_rel_path,
        env=env,
        engine=engine,
        run_mode=run_mode,
        flow_run_id=flow_run_id,
        attempt=attempt,
        outputs_prefix=outputs_prefix,
        resolved_commit=resolved_commit,
        inputs=inputs,
        job_name=job_name,
        engine_artifact_dir=engine_artifact_dir,
        engine_artifact_manifest_path=engine_artifact_manifest_path,
    )
    with maybe_start_mlflow_proxy(merged_env) as child_env:
        if run_mode == "repo":
            prepare_per_repo_venv(workdir, child_env)
        with (
            stdout_path.open("w", encoding="utf-8") as stdout_f,
            stderr_path.open("w", encoding="utf-8") as stderr_f,
        ):
            proc = subprocess.run(
                entrypoint,
                cwd=workdir,
                env=child_env,
                stdout=stdout_f,
                stderr=stderr_f,
                text=True,
            )

    result_path.write_text(
        json.dumps(
            {
                "exit_code": proc.returncode,
                "resolved_commit": resolved_commit,
                "run_mode": run_mode,
                "entrypoint": entrypoint,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    return RunArtifacts(
        workdir=workdir,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        result_path=result_path,
        engine_artifact_dir=engine_artifact_dir,
        engine_artifact_manifest_path=engine_artifact_manifest_path,
        exit_code=proc.returncode,
    )


def cleanup_workdir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _apply_runtime_env(
    *,
    merged_env: dict[str, str],
    workdir: Path,
    config_rel_path: str | None,
    env: dict[str, str] | None,
    engine: str,
    run_mode: str,
    flow_run_id: str,
    attempt: int,
    outputs_prefix: str,
    resolved_commit: str | None,
    inputs: dict[str, object] | None,
    job_name: str | None,
    engine_artifact_dir: Path,
    engine_artifact_manifest_path: Path,
) -> None:
    config_path = ""
    if config_rel_path:
        candidate = (workdir / config_rel_path).resolve()
        if not str(candidate).startswith(str(workdir.resolve()) + os.sep):
            raise RunnerError("config path escapes repository root")
        if not candidate.exists() or not candidate.is_file():
            raise RunnerError(f"config file not found: {config_rel_path}")
        config_path = str(candidate)
    merged_env.update(
        {
            "ORCH_ENGINE": engine,
            "ORCH_RUN_MODE": run_mode,
            "ORCH_FLOW_RUN_ID": flow_run_id,
            "ORCH_ATTEMPT": str(attempt),
            "ORCH_OUTPUTS_PREFIX": outputs_prefix,
            "ORCH_RESOLVED_COMMIT": resolved_commit or "",
            "ORCH_JOB_INPUTS_JSON": json.dumps(inputs or {}, ensure_ascii=True),
            "ORCH_ENGINE_ARTIFACT_DIR": str(engine_artifact_dir),
            "ORCH_ENGINE_ARTIFACT_MANIFEST_PATH": str(engine_artifact_manifest_path),
        }
    )
    if job_name:
        merged_env["ORCH_JOB_NAME"] = job_name
    if config_path:
        merged_env["ORCH_JOB_CONFIG_PATH"] = config_path
    if env:
        merged_env.update(env)
