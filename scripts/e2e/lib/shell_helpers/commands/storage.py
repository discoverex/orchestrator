from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from ..http import (
    artifact_api_base,
    download_headers,
    extract_json_object,
    http_json,
    http_text,
    rewrite_presigned_url,
)


def cmd_verify_storage_objects(args: argparse.Namespace) -> int:
    flow_run_id = args.flow_run_id
    gateway = artifact_api_base(args.storage_api_url)
    bucket = args.artifact_bucket
    log_dir = Path(args.log_dir)
    attempt = 1

    uris = {
        "stdout": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/stdout.log",
        "stderr": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/stderr.log",
        "result": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/result.json",
        "manifest": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/artifacts.json",
    }
    headers = {"Content-Type": "application/json"}
    if args.cf_access_client_id and args.cf_access_client_secret:
        headers["CF-Access-Client-Id"] = args.cf_access_client_id
        headers["CF-Access-Client-Secret"] = args.cf_access_client_secret

    for object_uri in uris.values():
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
        json.dumps(uris, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    if args.skip_engine_artifacts:
        return 0

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
        str(manifest_link.get("url", "")),
        args.presigned_internal_base_url,
    )
    d_headers = download_headers(args.presigned_host_header)
    if args.cf_access_client_id and args.cf_access_client_secret:
        d_headers["CF-Access-Client-Id"] = args.cf_access_client_id
        d_headers["CF-Access-Client-Secret"] = args.cf_access_client_secret
    manifest = cast(
        dict[str, object],
        json.loads(http_text(manifest_url, headers=d_headers, timeout=15)),
    )

    if manifest.get("flow_run_id") != flow_run_id:
        raise SystemExit("manifest flow_run_id mismatch")
    manifest_attempt = manifest.get("attempt", -1)
    if int(str(manifest_attempt)) != attempt:
        raise SystemExit("manifest attempt mismatch")

    rows = manifest.get("artifacts", [])
    if not isinstance(rows, list):
        raise SystemExit("manifest artifacts mismatch")
    kinds = {
        row.get("kind"): row.get("object_uri") for row in rows if isinstance(row, dict)
    }
    for kind in ("stdout", "stderr", "result"):
        if kinds.get(kind) != uris[kind]:
            raise SystemExit(f"manifest {kind} uri mismatch")

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
        str(stdout_link.get("url", "")),
        args.presigned_internal_base_url,
    )
    result_link = http_json(
        "POST",
        f"{gateway}/v1/presign/get",
        payload={
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "kind": "result",
            "filename": "result.json",
        },
        headers=headers,
        timeout=10,
    )
    result_url = rewrite_presigned_url(
        str(result_link.get("url", "")),
        args.presigned_internal_base_url,
    )
    result_payload = cast(
        dict[str, object],
        json.loads(http_text(result_url, headers=d_headers, timeout=15)),
    )
    exit_code = int(str(result_payload.get("exit_code", -1)))
    if exit_code != 0:
        raise SystemExit(f"engine entrypoint exited with code {exit_code}")

    engine_output = extract_json_object(
        http_text(stdout_url, headers=d_headers, timeout=15)
    )
    (log_dir / "engine_output.json").write_text(
        json.dumps(engine_output, ensure_ascii=True, indent=2), encoding="utf-8"
    )

    from .storage_engine import verify_engine_artifacts

    verify_engine_artifacts(args, engine_output, gateway, headers, d_headers)
    return 0


def cmd_uri_host(args: argparse.Namespace) -> int:
    host = urlsplit(args.uri).hostname or ""
    if not host:
        raise SystemExit("unable to parse host from uri")
    print(host)
    return 0


def cmd_verify_flush_output(args: argparse.Namespace) -> int:
    payload = cast(
        dict[str, object],
        json.loads(Path(args.output_json).read_text(encoding="utf-8")),
    )
    uploaded_raw = payload.get("uploaded", [])
    if not isinstance(uploaded_raw, list):
        raise SystemExit("flush output uploaded field is not a list")
    uploaded = [row for row in uploaded_raw if isinstance(row, dict)]
    if not any(row.get("flow_run_id") == args.flow_run_id for row in uploaded):
        raise SystemExit("flush did not export current flow run")
    print("flush-ok")
    return 0
