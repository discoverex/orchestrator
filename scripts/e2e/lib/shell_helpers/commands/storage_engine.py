from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from ..http import (
    http_json,
    http_text,
    rewrite_presigned_url,
)


def verify_engine_artifacts(
    args: argparse.Namespace,
    engine_output: dict[str, object],
    gateway: str,
    headers: dict[str, str],
    d_headers: dict[str, str],
) -> None:
    flow_run_id = args.flow_run_id
    bucket = args.artifact_bucket
    log_dir = Path(args.log_dir)
    attempt = 1

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

    engine_manifest_link = http_json(
        "POST",
        f"{gateway}/v1/presign/get",
        payload={
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "kind": "custom",
            "filename": "engine-artifacts.json",
        },
        headers=headers,
        timeout=10,
    )
    engine_manifest_url = rewrite_presigned_url(
        str(engine_manifest_link.get("url", "")),
        args.presigned_internal_base_url,
    )
    engine_manifest = cast(
        dict[str, object],
        json.loads(http_text(engine_manifest_url, headers=d_headers, timeout=15)),
    )
    if engine_manifest.get("flow_run_id") != flow_run_id:
        raise SystemExit("engine manifest flow_run_id mismatch")
    if int(str(engine_manifest.get("attempt", -1))) != attempt:
        raise SystemExit("engine manifest attempt mismatch")
    manifest_rows = engine_manifest.get("artifacts", [])
    if not isinstance(manifest_rows, list):
        raise SystemExit("engine manifest artifacts mismatch")
    by_logical_name = {
        str(row.get("logical_name")): str(row.get("object_uri"))
        for row in manifest_rows
        if isinstance(row, dict)
    }
    if by_logical_name.get("scene_json") != engine_uris["scene_json"]:
        raise SystemExit("engine manifest scene_json uri mismatch")
    if by_logical_name.get("verification_json") != engine_uris["verification_json"]:
        raise SystemExit("engine manifest verification_json uri mismatch")

    (log_dir / "engine_uris.json").write_text(
        json.dumps(engine_uris, ensure_ascii=True, indent=2), encoding="utf-8"
    )
