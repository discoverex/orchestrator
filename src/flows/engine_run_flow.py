from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib import request

from prefect import flow, task
from prefect.context import get_run_context
from prefect.runtime import flow_run

from src.runner.git_runner import cleanup_workdir, resolve_commit, run_entrypoint


@dataclass(frozen=True)
class ArtifactLink:
    kind: str
    object_uri: str
    url: str


def _gateway_headers() -> dict[str, str]:
    token = os.getenv("STORAGE_GATEWAY_TOKEN", "dev-storage-token")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _http_json(method: str, url: str, payload: dict[str, object]) -> dict[str, object] | list[dict[str, object]]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, method=method, data=body, headers=_gateway_headers())
    with request.urlopen(req) as resp:  # nosec B310 - controlled endpoint from env
        return json.loads(resp.read().decode("utf-8"))


def _upload_file(put_url: str, path: Path) -> None:
    data = path.read_bytes()
    req = request.Request(put_url, method="PUT", data=data, headers={"Content-Type": "application/octet-stream"})
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
def upload_outputs_task(links: list[ArtifactLink], local_paths: dict[str, str], flow_run_id: str, attempt: int) -> dict[str, str]:
    output: dict[str, str] = {}
    for link in links:
        if link.kind == "manifest":
            manifest = {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "artifacts": [{"kind": k, "object_uri": v} for k, v in output.items()],
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
) -> dict[str, object]:
    _ = (inputs_ref, outputs_prefix)
    run_id = flow_run.get_id()
    try:
        attempt = int(get_run_context().flow_run.run_count or 1)
    except Exception:
        attempt = 1
    resolved_commit = resolve_commit_task(repo_url, ref)
    links = prepare_manifest_task(run_id, attempt)
    local_paths, exit_code = run_entrypoint_task(repo_url, resolved_commit, entrypoint, env or {})
    uploaded = upload_outputs_task(links, local_paths, run_id, attempt)
    cleanup_workdir(Path(local_paths["workdir"]))

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
