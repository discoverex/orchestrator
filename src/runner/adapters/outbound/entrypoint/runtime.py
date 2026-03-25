from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from runner.adapters.outbound.git.repo import RunnerError

logger = logging.getLogger("runner.entrypoint")


def apply_worker_runtime_defaults(
    merged_env: dict[str, str],
    *,
    explicit_env_keys: set[str] | None = None,
) -> None:
    explicit_env_keys = explicit_env_keys or set()
    runtime_root = merged_env.get("ORCH_WORKER_RUNTIME_DIR", "").strip()
    if not runtime_root:
        runtime_root = "/var/lib/orchestrator"
        merged_env["ORCH_WORKER_RUNTIME_DIR"] = runtime_root

    cache_dir = ""
    if "ORCH_CACHE_DIR" in explicit_env_keys:
        cache_dir = merged_env.get("ORCH_CACHE_DIR", "").strip()
    if not cache_dir:
        repo_cache_dir = (
            merged_env.get("ORCH_REPO_CACHE_DIR", "").strip()
            if "ORCH_REPO_CACHE_DIR" in explicit_env_keys
            else ""
        )
        model_cache_dir = (
            merged_env.get("ORCH_MODEL_CACHE_DIR", "").strip()
            if "ORCH_MODEL_CACHE_DIR" in explicit_env_keys
            else ""
        )
        if repo_cache_dir:
            cache_dir = str(Path(repo_cache_dir).parent)
        elif model_cache_dir:
            cache_dir = str(Path(model_cache_dir).parent)
        else:
            cache_dir = str(Path(runtime_root) / "cache")
        merged_env["ORCH_CACHE_DIR"] = cache_dir

    repo_cache_dir = (
        merged_env.get("ORCH_REPO_CACHE_DIR", "").strip()
        if "ORCH_REPO_CACHE_DIR" in explicit_env_keys
        else ""
    )
    if not repo_cache_dir:
        repo_cache_dir = str(Path(cache_dir) / "repo")
        merged_env["ORCH_REPO_CACHE_DIR"] = repo_cache_dir

    repo_runtime_dir = (
        merged_env.get("ORCH_REPO_RUNTIME_DIR", "").strip()
        if "ORCH_REPO_RUNTIME_DIR" in explicit_env_keys
        else ""
    )
    if not repo_runtime_dir:
        repo_runtime_dir = str(Path(runtime_root) / "repos")
        merged_env["ORCH_REPO_RUNTIME_DIR"] = repo_runtime_dir

    model_cache_dir = (
        merged_env.get("ORCH_MODEL_CACHE_DIR", "").strip()
        if "ORCH_MODEL_CACHE_DIR" in explicit_env_keys
        else ""
    )
    if not model_cache_dir:
        model_cache_dir = str(Path(cache_dir) / "models")
        merged_env["ORCH_MODEL_CACHE_DIR"] = model_cache_dir

    merged_env.setdefault("HF_HOME", model_cache_dir)
    merged_env.setdefault("HF_HUB_CACHE", str(Path(model_cache_dir) / "hub"))
    merged_env.setdefault(
        "TRANSFORMERS_CACHE", str(Path(model_cache_dir) / "transformers")
    )
    merged_env.setdefault("TORCH_HOME", str(Path(model_cache_dir) / "torch"))


def env_summary(env: dict[str, str]) -> dict[str, str]:
    summary: dict[str, str] = {}
    for key in (
        "ORCH_ENGINE",
        "ORCH_RUN_MODE",
        "ORCH_FLOW_RUN_ID",
        "ORCH_ATTEMPT",
        "ORCH_OUTPUTS_PREFIX",
        "ORCH_RESOLVED_COMMIT",
        "ORCH_JOB_NAME",
        "ORCH_JOB_CONFIG_PATH",
        "ORCH_ENGINE_ARTIFACT_DIR",
        "ORCH_ENGINE_ARTIFACT_MANIFEST_PATH",
        "ORCH_WORKER_RUNTIME_DIR",
        "ORCH_CACHE_DIR",
        "ORCH_REPO_CACHE_DIR",
        "ORCH_REPO_RUNTIME_DIR",
        "ORCH_MODEL_CACHE_DIR",
        "MLFLOW_TRACKING_URI",
        "STORAGE_API_URL",
    ):
        value = env.get(key)
        if value:
            summary[key] = value
    return summary


def prepare_per_repo_venv(workdir: Path, merged_env: dict[str, str]) -> None:
    uv_bin = shutil.which("uv")
    if not uv_bin:
        logger.info(
            "uv not found; skipping per-repo venv",
            extra={"workdir": str(workdir)},
        )
        return

    venv_dir = workdir / ".venv"
    merged_env["UV_PROJECT_ENVIRONMENT"] = str(venv_dir)
    merged_env["PATH"] = f"{venv_dir / 'bin'}:{merged_env.get('PATH', '')}"
    if not (workdir / "pyproject.toml").exists():
        logger.info(
            "pyproject missing; skipping per-repo venv sync",
            extra={"workdir": str(workdir)},
        )
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
        logger.error(
            "per-repo venv sync failed",
            extra={
                "workdir": str(workdir),
                "cmd": sync_cmd,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            },
        )
        raise RunnerError(
            f"venv setup failed: {' '.join(sync_cmd)}\n{proc.stderr.strip()}"
        )
    logger.info(
        "per-repo venv ready",
        extra={"workdir": str(workdir), "cmd": sync_cmd, "venv_dir": str(venv_dir)},
    )


def apply_runtime_env(
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
    explicit_env_keys = set(env or {})
    if env:
        merged_env.update(env)
    apply_worker_runtime_defaults(merged_env, explicit_env_keys=explicit_env_keys)
