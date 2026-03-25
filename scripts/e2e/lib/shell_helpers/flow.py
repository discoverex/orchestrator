from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast
from urllib import error

from scripts.e2e.lib.shell_helpers.http import (
    artifact_api_base,
    download_headers,
    extract_json_object,
    http_json,
    http_text,
    rewrite_presigned_url,
)


def poll_prefect_completion(
    prefect_api_url: str, flow_run_id: str, timeout_sec: int
) -> int:
    api_url = prefect_api_url.rstrip("/")
    deadline = time.time() + timeout_sec
    transient_statuses = {403, 404, 429, 500, 502, 503, 504}
    while time.time() < deadline:
        try:
            payload = cast(
                dict[str, Any],
                http_json("GET", f"{api_url}/flow_runs/{flow_run_id}", timeout=10),
            )
        except error.HTTPError as exc:
            if exc.code in transient_statuses:
                time.sleep(2)
                continue
            raise
        state_raw = payload.get("state")
        state: dict[str, Any] = state_raw if isinstance(state_raw, dict) else {}
        state_type = str(payload.get("state_type") or state.get("type") or "").upper()
        if state_type == "COMPLETED":
            print("COMPLETED")
            return 0
        if state_type in {"FAILED", "CRASHED", "CANCELLED"}:
            print(state_type)
            return 2
        time.sleep(2)
    print("TIMEOUT")
    return 3


def verify_storage_objects(args: Any) -> int:
    flow_run_id = args.flow_run_id
    gateway = artifact_api_base(args.storage_api_url)
    bucket = args.artifact_bucket
    log_dir = Path(args.log_dir)
    attempt = 1
    flow_uris = {
        "stdout": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/stdout.log",
        "stderr": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/stderr.log",
        "result": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/result.json",
        "manifest": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/artifacts.json",
    }
    headers = {"Content-Type": "application/json"}
    if args.cf_access_client_id and args.cf_access_client_secret:
        headers["CF-Access-Client-Id"] = args.cf_access_client_id
        headers["CF-Access-Client-Secret"] = args.cf_access_client_secret
    for object_uri in flow_uris.values():
        payload = http_json(
            "POST",
            f"{gateway}/v1/object/head",
            payload={"object_uri": object_uri},
            headers=headers,
            timeout=10,
        )
        if not payload.get("exists"):
            raise SystemExit(f"missing object: {object_uri}")
    (log_dir / "flow_uris.json").write_text(
        json.dumps(flow_uris, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    if args.skip_engine_artifacts:
        return 0
    download = download_headers(args.presigned_host_header)
    if args.cf_access_client_id and args.cf_access_client_secret:
        download["CF-Access-Client-Id"] = args.cf_access_client_id
        download["CF-Access-Client-Secret"] = args.cf_access_client_secret
    _verify_flow_manifest(
        gateway,
        flow_run_id,
        attempt,
        headers,
        download,
        args.presigned_internal_base_url,
    )
    _verify_engine_artifacts(
        gateway,
        flow_run_id,
        attempt,
        bucket,
        headers,
        download,
        args.presigned_internal_base_url,
        log_dir,
    )
    return 0


def _verify_flow_manifest(
    gateway: str,
    flow_run_id: str,
    attempt: int,
    headers: dict[str, str],
    download: dict[str, str],
    internal_base_url: str,
) -> None:
    manifest_link = http_json(
        "POST",
        f"{gateway}/v1/presign/get",
        payload={
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "kind": "manifest",
            "filename": "artifacts.json",
        },
        headers=headers,
        timeout=10,
    )
    manifest_url = rewrite_presigned_url(
        str(manifest_link.get("url", "")), internal_base_url
    )
    manifest = cast(
        dict[str, object],
        json.loads(http_text(manifest_url, headers=download, timeout=15)),
    )
    if (
        manifest.get("flow_run_id") != flow_run_id
        or int(str(manifest.get("attempt", -1))) != attempt
    ):
        raise SystemExit("manifest metadata mismatch")


def _verify_engine_artifacts(
    gateway: str,
    flow_run_id: str,
    attempt: int,
    bucket: str,
    headers: dict[str, str],
    download: dict[str, str],
    internal_base_url: str,
    log_dir: Path,
) -> None:
    stdout_link = http_json(
        "POST",
        f"{gateway}/v1/presign/get",
        payload={
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "kind": "stdout",
            "filename": "stdout.log",
        },
        headers=headers,
        timeout=10,
    )
    stdout_url = rewrite_presigned_url(
        str(stdout_link.get("url", "")), internal_base_url
    )
    engine_output = extract_json_object(
        http_text(stdout_url, headers=download, timeout=15)
    )
    (log_dir / "engine_output.json").write_text(
        json.dumps(engine_output, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    scene_id = str(engine_output.get("scene_id", "")).strip()
    version_id = str(engine_output.get("version_id", "")).strip()
    if not scene_id or not version_id:
        raise SystemExit("engine stdout missing scene_id/version_id")
    engine_uris = {
        "scene_json": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/engine/scene/scene.json",
        "verification_json": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/engine/scene/verification.json",
        "engine_manifest": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/engine-artifacts.json",
    }
    for object_uri in engine_uris.values():
        payload = http_json(
            "POST",
            f"{gateway}/v1/object/head",
            payload={"object_uri": object_uri},
            headers=headers,
            timeout=10,
        )
        if not payload.get("exists"):
            raise SystemExit(f"missing engine object: {object_uri}")
    (log_dir / "engine_uris.json").write_text(
        json.dumps(engine_uris, ensure_ascii=True, indent=2), encoding="utf-8"
    )
