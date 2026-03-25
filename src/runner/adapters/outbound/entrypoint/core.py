"""Execution adapter for materializing source and launching engine entrypoints."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from runner.adapters.outbound.entrypoint.runtime import (
    apply_runtime_env,
    env_summary,
    prepare_per_repo_venv,
)
from runner.adapters.outbound.git.repo import (
    RunnerError,
    prepare_runtime_repo,
)
from runner.adapters.outbound.mlflow.proxy import maybe_start_mlflow_proxy
from runner.domain.models import RunArtifacts

logger = logging.getLogger("runner.entrypoint")


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
    workdir: Path | None = None
    logger.info(
        "starting entrypoint run",
        extra={
            "workdir": "",
            "run_mode": run_mode,
            "engine": engine,
            "repo_url": repo_url or "",
            "ref": ref or "",
            "resolved_commit": resolved_commit or "",
            "attempt": attempt,
            "flow_run_id": flow_run_id,
            "job_name": job_name or "",
        },
    )
    if run_mode == "repo":
        if not repo_url or not ref or not resolved_commit:
            raise RunnerError(
                "repo_url/ref/resolved_commit are required when run_mode=repo"
            )
        workdir = prepare_runtime_repo(repo_url, ref, resolved_commit)
        logger.info(
            "prepared repo-backed workdir",
            extra={"workdir": str(workdir), "repo_url": repo_url, "ref": ref},
        )
    elif run_mode == "inline":
        import tempfile

        workdir = Path(tempfile.mkdtemp(prefix="orchestrator-run-"))
        if config_rel_path:
            raise RunnerError("config is not supported when run_mode=inline")
    else:
        raise RunnerError(f"unsupported run_mode: {run_mode}")

    assert workdir is not None

    stdout_path = workdir / "stdout.log"
    stderr_path = workdir / "stderr.log"
    result_path = workdir / "result.json"
    engine_artifact_dir = workdir / "engine-artifacts"
    engine_artifact_manifest_path = workdir / "engine-artifacts.manifest.json"
    engine_artifact_dir.mkdir(parents=True, exist_ok=True)

    merged_env = os.environ.copy()
    apply_runtime_env(
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
    logger.info(
        "runtime environment prepared",
        extra={
            "workdir": str(workdir),
            "env": env_summary(merged_env),
            "entrypoint": entrypoint,
        },
    )
    with maybe_start_mlflow_proxy(merged_env) as child_env:
        if run_mode == "repo":
            prepare_per_repo_venv(workdir, child_env)
        with (
            stdout_path.open("w", encoding="utf-8") as stdout_f,
            stderr_path.open("w", encoding="utf-8") as stderr_f,
        ):
            logger.info(
                "launching child entrypoint",
                extra={"workdir": str(workdir), "entrypoint": entrypoint},
            )
            proc = subprocess.run(
                entrypoint,
                cwd=workdir,
                env=child_env,
                stdout=stdout_f,
                stderr=stderr_f,
                text=True,
            )
    logger.info(
        "child entrypoint finished",
        extra={
            "workdir": str(workdir),
            "entrypoint": entrypoint,
            "exit_code": proc.returncode,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "result_path": str(result_path),
        },
    )

    result_path.write_text(
        json.dumps(
            {
                "exit_code": proc.returncode,
                "resolved_commit": resolved_commit,
                "run_mode": run_mode,
                "entrypoint": entrypoint,
                "workdir": str(workdir),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "env_summary": env_summary(merged_env),
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
    logger.info("cleaning up workdir", extra={"workdir": str(path)})
    shutil.rmtree(path, ignore_errors=True)
