"""Execution adapter for materializing source and launching engine entrypoints."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from urllib.parse import unquote, urlsplit

from .mlflow_proxy import maybe_start_mlflow_proxy
from .models import RunArtifacts

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_GITHUB_SSH = re.compile(r"^git@github\.com:(?P<repo>.+?)(?:\.git)?$")


class RunnerError(RuntimeError):
    pass


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RunnerError(f"command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def _repo_cache_root() -> Path:
    return Path(os.getenv("ORCH_REPO_CACHE_DIR", "/tmp/orchestrator-repo-cache"))


def _repo_cache_path(repo_url: str) -> Path:
    key = sha256(repo_url.encode("utf-8")).hexdigest()[:16]
    return _repo_cache_root() / key


def _normalized_repo_url(repo_url: str) -> str:
    match = _GITHUB_SSH.match(repo_url.strip())
    if not match:
        return repo_url
    return f"https://github.com/{match.group('repo')}.git"


def _local_repo_path(repo_url: str) -> Path | None:
    split = urlsplit(repo_url)
    if split.scheme == "file":
        return Path(unquote(split.path))
    if split.scheme:
        return None
    candidate = Path(repo_url)
    if candidate.exists():
        return candidate
    return None


def _safe_directory_args(repo_path: Path) -> list[str]:
    resolved = repo_path.resolve()
    return [
        "-c",
        f"safe.directory={resolved}",
        "-c",
        f"safe.directory={resolved / '.git'}",
    ]


def _checkout_target(ref: str | None, resolved_commit: str) -> str:
    candidate = (ref or "").strip()
    if candidate and not _SHA1.match(candidate.lower()):
        return candidate
    return resolved_commit


def _prepare_cached_repo(repo_url: str, ref: str | None, resolved_commit: str) -> Path:
    normalized_repo_url = _normalized_repo_url(repo_url)
    cache_root = _repo_cache_root()
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_repo = _repo_cache_path(normalized_repo_url)
    local_repo = _local_repo_path(normalized_repo_url)
    clone_source = (
        local_repo.resolve().as_uri() if local_repo is not None else normalized_repo_url
    )

    if (cache_repo / ".git").exists():
        _run(["git", "fetch", "--all", "--tags", "--prune"], cwd=cache_repo)
    else:
        if cache_repo.exists():
            shutil.rmtree(cache_repo, ignore_errors=True)
        clone_cmd = ["git"]
        if local_repo is not None:
            clone_cmd.extend(_safe_directory_args(local_repo))
        clone_cmd.extend(["clone", "--filter=blob:none", clone_source, str(cache_repo)])
        _run(clone_cmd)

    checkout_target = _checkout_target(ref, resolved_commit)
    _run(["git", "checkout", checkout_target], cwd=cache_repo)
    _run(["git", "reset", "--hard"], cwd=cache_repo)
    _run(["git", "clean", "-fdx"], cwd=cache_repo)
    return cache_repo


def _prepare_per_repo_venv(workdir: Path, merged_env: dict[str, str]) -> None:
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


def resolve_commit(repo_url: str, ref: str) -> str:
    candidate = ref.strip().lower()
    if _SHA1.match(candidate):
        return candidate

    normalized_repo_url = _normalized_repo_url(repo_url)
    local_repo = _local_repo_path(normalized_repo_url)
    if local_repo is not None:
        return _run(
            [
                "git",
                *_safe_directory_args(local_repo),
                "-C",
                str(local_repo),
                "rev-parse",
                ref,
            ]
        )

    for remote_ref in (f"refs/heads/{ref}", f"refs/tags/{ref}", ref):
        try:
            out = _run(["git", "ls-remote", normalized_repo_url, remote_ref])
        except RunnerError:
            continue
        if not out:
            continue
        line = out.splitlines()[0]
        commit = line.split()[0]
        if _SHA1.match(commit):
            return commit
    raise RunnerError(f"unable to resolve ref={ref} for repo={repo_url}")


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
        if not repo_url:
            raise RunnerError("repo_url is required when run_mode=repo")
        if not ref:
            raise RunnerError("ref is required when run_mode=repo")
        if not resolved_commit:
            raise RunnerError("resolved_commit is required when run_mode=repo")
        cached_repo = _prepare_cached_repo(repo_url, ref, resolved_commit)
        _run(["git", "clone", "--no-checkout", str(cached_repo), str(workdir)])
        _run(["git", "checkout", _checkout_target(ref, resolved_commit)], cwd=workdir)
    elif run_mode == "inline":
        if config_rel_path:
            raise RunnerError("config is not supported when run_mode=inline")
    else:
        raise RunnerError(f"unsupported run_mode: {run_mode}")

    stdout_path = workdir / "stdout.log"
    stderr_path = workdir / "stderr.log"
    result_path = workdir / "result.json"

    merged_env = os.environ.copy()
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
        }
    )
    if job_name:
        merged_env["ORCH_JOB_NAME"] = job_name
    if config_path:
        merged_env["ORCH_JOB_CONFIG_PATH"] = config_path

    if env:
        merged_env.update(env)

    with maybe_start_mlflow_proxy(merged_env) as child_env:
        if run_mode == "repo":
            _prepare_per_repo_venv(workdir, child_env)

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
        exit_code=proc.returncode,
    )


def cleanup_workdir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
