"""Execution adapter for materializing source and launching engine flows."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import sys
import traceback
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from prefect import flow
from prefect.settings import (
    PREFECT_API_URL,
    PREFECT_CLIENT_CUSTOM_HEADERS,
    temporary_settings,
)

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


@contextlib.contextmanager
def _patched_environ(values: dict[str, str]) -> Iterator[None]:
    original = os.environ.copy()
    os.environ.clear()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


@contextlib.contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


@contextlib.contextmanager
def _patched_sys_path(paths: list[Path]) -> Iterator[None]:
    original = list(sys.path)
    prefixes = [str(path) for path in paths if path.exists()]
    sys.path[:0] = prefixes
    try:
        yield
    finally:
        sys.path[:] = original


def _jsonable_result(value: object) -> object:
    try:
        json.dumps(value, ensure_ascii=True)
        return value
    except TypeError:
        return repr(value)


def _prepare_child_prefect_env(env: dict[str, str], workdir: Path) -> dict[str, str]:
    sanitized = env.copy()
    # Child repo flows run as local subflows under the runner runtime; they should
    # not open a second client session against the worker's Prefect API.
    for key in (
        "PREFECT_API_URL",
        "PREFECT_CLIENT_CUSTOM_HEADERS",
    ):
        sanitized.pop(key, None)
    sanitized.setdefault("PREFECT_HOME", str(workdir / ".prefect"))
    return sanitized


def run_entrypoint(
    repo_url: str | None,
    ref: str | None,
    resolved_commit: str | None,
    flow_entrypoint: str,
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
    logger.info(
        "starting flow entrypoint run",
        extra={
            "workdir": "",
            "run_mode": run_mode,
            "engine": engine,
            "repo_url": repo_url or "",
            "ref": ref or "",
            "resolved_commit": resolved_commit or "",
            "flow_entrypoint": flow_entrypoint,
            "attempt": attempt,
            "flow_run_id": flow_run_id,
            "job_name": job_name or "",
        },
    )
    if run_mode != "repo":
        raise RunnerError("flow_entrypoint execution requires run_mode=repo")
    if not repo_url or not ref or not resolved_commit:
        raise RunnerError("repo_url/ref/resolved_commit are required when run_mode=repo")

    workdir = prepare_runtime_repo(repo_url, ref, resolved_commit)
    logger.info(
        "prepared repo-backed workdir",
        extra={"workdir": str(workdir), "repo_url": repo_url, "ref": ref},
    )

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
            "flow_entrypoint": flow_entrypoint,
        },
    )

    exit_code = 0
    child_result: object = None
    with maybe_start_mlflow_proxy(merged_env) as proxied_env:
        child_env = _prepare_child_prefect_env(proxied_env, workdir)
        prepare_per_repo_venv(workdir, child_env)
        with (
            stdout_path.open("w", encoding="utf-8") as stdout_f,
            stderr_path.open("w", encoding="utf-8") as stderr_f,
            contextlib.redirect_stdout(stdout_f),
            contextlib.redirect_stderr(stderr_f),
            _patched_environ(child_env),
            _working_directory(workdir),
            _patched_sys_path([workdir / "src", workdir]),
            temporary_settings(
                restore_defaults={
                    PREFECT_API_URL,
                    PREFECT_CLIENT_CUSTOM_HEADERS,
                }
            ),
        ):
            try:
                source_flow = flow.from_source(
                    source=str(workdir), entrypoint=flow_entrypoint
                )
                logger.info(
                    "launching child flow entrypoint",
                    extra={"workdir": str(workdir), "flow_entrypoint": flow_entrypoint},
                )
                child_result = source_flow(**dict(inputs or {}))
            except Exception:
                exit_code = 1
                traceback.print_exc(file=stderr_f)

    logger.info(
        "child flow entrypoint finished",
        extra={
            "workdir": str(workdir),
            "flow_entrypoint": flow_entrypoint,
            "exit_code": exit_code,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "result_path": str(result_path),
        },
    )

    result_path.write_text(
        json.dumps(
            {
                "exit_code": exit_code,
                "resolved_commit": resolved_commit,
                "run_mode": run_mode,
                "flow_entrypoint": flow_entrypoint,
                "workdir": str(workdir),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "env_summary": env_summary(merged_env),
                "result": _jsonable_result(child_result),
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
        exit_code=exit_code,
    )


def cleanup_workdir(path: Path) -> None:
    logger.info("cleaning up workdir", extra={"workdir": str(path)})
    shutil.rmtree(path, ignore_errors=True)
