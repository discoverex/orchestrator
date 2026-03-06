from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import request

from prefect import flow, task
from prefect.context import get_run_context
from prefect.runtime import flow_run

from flows.checkpoint_store import load_checkpoint, resolve_checkpoint_path, save_checkpoint
from runner.git_runner import cleanup_workdir, resolve_commit, run_entrypoint

WORKER_HTTP_USER_AGENT = "orchestrator-worker/1.0"


@dataclass(frozen=True)
class ArtifactLink:
    kind: str
    object_uri: str
    url: str


def _step_done(state: dict[str, Any], step: str) -> bool:
    return bool(state.get("steps", {}).get(step))


def _mark_step(state: dict[str, Any], step: str) -> None:
    steps = state.setdefault("steps", {})
    steps[step] = True


def _artifact_paths_exist(local_paths: dict[str, str]) -> bool:
    return all(Path(local_paths[k]).exists() for k in ("stdout", "stderr", "result"))


def _gateway_headers() -> dict[str, str]:
    token = os.getenv("STORAGE_GATEWAY_TOKEN", "dev-storage-token")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": WORKER_HTTP_USER_AGENT,
    }


def _http_json(method: str, url: str, payload: dict[str, object]) -> dict[str, object] | list[dict[str, object]]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method=method, data=body, headers=_gateway_headers())
    with request.urlopen(req) as resp:  # nosec B310 - controlled endpoint from env
        return json.loads(resp.read().decode("utf-8"))


def _upload_file(put_url: str, path: Path) -> None:
    data = path.read_bytes()
    req = request.Request(
        put_url,
        method="PUT",
        data=data,
        headers={
            "Content-Type": "application/octet-stream",
            "User-Agent": WORKER_HTTP_USER_AGENT,
        },
    )
    with request.urlopen(req):  # nosec B310 - presigned URL
        return


@task
def resolve_commit_task(repo_url: str, ref: str) -> str:
    return resolve_commit(repo_url, ref)


@task
def prepare_manifest_task(flow_run_id: str, attempt: int) -> list[ArtifactLink]:
    gateway = os.getenv("STORAGE_GATEWAY_URL", "http://127.0.0.1:18100")
    payload = {
        "flow_run_id": flow_run_id,
        "attempt": attempt,
        "entries": [
            {"flow_run_id": flow_run_id, "attempt": attempt, "kind": "stdout", "filename": "stdout.log"},
            {"flow_run_id": flow_run_id, "attempt": attempt, "kind": "stderr", "filename": "stderr.log"},
            {"flow_run_id": flow_run_id, "attempt": attempt, "kind": "result", "filename": "result.json"},
            {"flow_run_id": flow_run_id, "attempt": attempt, "kind": "manifest", "filename": "artifacts.json"},
        ],
    }
    rows = _http_json("POST", f"{gateway}/v1/presign/batch", payload)
    assert isinstance(rows, list)
    return [ArtifactLink(kind=str(r["kind"]), object_uri=str(r["object_uri"]), url=str(r["url"])) for r in rows]


@task
def run_entrypoint_task(repo_url: str, resolved_commit: str, entrypoint: list[str], env: dict[str, str]) -> tuple[dict[str, str], int]:
    artifacts = run_entrypoint(repo_url=repo_url, resolved_commit=resolved_commit, entrypoint=entrypoint, env=env)
    paths = {
        "workdir": str(artifacts.workdir),
        "stdout": str(artifacts.stdout_path),
        "stderr": str(artifacts.stderr_path),
        "result": str(artifacts.result_path),
    }
    return paths, artifacts.exit_code


@task(retries=2, retry_delay_seconds=10)
def upload_outputs_task(
    links: list[ArtifactLink],
    local_paths: dict[str, str],
    flow_run_id: str,
    attempt: int,
    already_uploaded: dict[str, str] | None = None,
) -> dict[str, str]:
    output: dict[str, str] = dict(already_uploaded or {})
    for link in links:
        if link.kind in output:
            continue
        if link.kind == "manifest":
            manifest = {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "artifacts": [{"kind": k, "object_uri": v} for k, v in output.items() if k != "manifest"],
            }
            manifest_path = Path(local_paths["result"]).parent / "artifacts.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
            _upload_file(link.url, manifest_path)
            output["manifest"] = link.object_uri
            continue

        src = Path(local_paths[link.kind])
        _upload_file(link.url, src)
        output[link.kind] = link.object_uri
    return output


@flow(name="engine-run", retries=3, retry_delay_seconds=30)
def engine_run_flow(
    repo_url: str,
    ref: str,
    entrypoint: list[str],
    inputs_ref: list[str] | None = None,
    env: dict[str, str] | None = None,
    outputs_prefix: str | None = None,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, object]:
    _ = (inputs_ref, outputs_prefix)
    run_id = flow_run.get_id()
    active_resume_key = resume_key or run_id
    checkpoint_path = resolve_checkpoint_path(
        checkpoint_dir=checkpoint_dir or os.getenv("ORCHESTRATOR_CHECKPOINT_DIR"),
        resume_key=active_resume_key,
    )
    state = load_checkpoint(checkpoint_path)
    state.setdefault("flow_run_id", run_id)
    state.setdefault("resume_key", active_resume_key)
    state.setdefault("steps", {})

    try:
        attempt = int(get_run_context().flow_run.run_count or 1)
    except Exception:
        attempt = 1
    state["attempt"] = attempt
    save_checkpoint(checkpoint_path, state)

    if _step_done(state, "resolve_commit"):
        resolved_commit = str(state["resolved_commit"])
    else:
        resolved_commit = resolve_commit_task(repo_url, ref)
        state["resolved_commit"] = resolved_commit
        _mark_step(state, "resolve_commit")
        save_checkpoint(checkpoint_path, state)

    local_paths = state.get("local_paths", {})
    if _step_done(state, "run_entrypoint") and isinstance(local_paths, dict) and not _artifact_paths_exist(local_paths):
        state["steps"]["run_entrypoint"] = False
        for key in ("stdout_uploaded", "stderr_uploaded", "result_uploaded", "manifest_uploaded", "cleanup"):
            state["steps"][key] = False
        state["uploaded"] = {}
        save_checkpoint(checkpoint_path, state)

    if _step_done(state, "run_entrypoint"):
        local_paths = state["local_paths"]
        exit_code = int(state.get("exit_code", 1))
    else:
        local_paths, exit_code = run_entrypoint_task(repo_url, resolved_commit, entrypoint, env or {})
        state["local_paths"] = local_paths
        state["exit_code"] = exit_code
        _mark_step(state, "run_entrypoint")
        state["steps"]["cleanup"] = False
        save_checkpoint(checkpoint_path, state)

    if _step_done(state, "manifest_uploaded"):
        uploaded = dict(state.get("uploaded", {}))
    else:
        links = prepare_manifest_task(run_id, attempt)
        _mark_step(state, "prepare_manifest")
        state["links"] = [link.__dict__ for link in links]
        save_checkpoint(checkpoint_path, state)

        uploaded = upload_outputs_task(
            links,
            local_paths,
            run_id,
            attempt,
            already_uploaded=state.get("uploaded", {}),
        )
        state["uploaded"] = uploaded
        for key in ("stdout", "stderr", "result", "manifest"):
            if key in uploaded:
                _mark_step(state, f"{key}_uploaded")
        save_checkpoint(checkpoint_path, state)

    workdir = Path(local_paths["workdir"])
    if not _step_done(state, "cleanup") and workdir.exists():
        cleanup_workdir(workdir)
        _mark_step(state, "cleanup")
        save_checkpoint(checkpoint_path, state)

    return {
        "flow_run_id": run_id,
        "attempt": attempt,
        "resolved_commit": resolved_commit,
        "outputs_prefix": f"jobs/{run_id}/attempt-{attempt}/",
        "stdout_uri": uploaded.get("stdout"),
        "stderr_uri": uploaded.get("stderr"),
        "result_uri": uploaded.get("result"),
        "manifest_uri": uploaded.get("manifest"),
        "exit_code": exit_code,
    }
