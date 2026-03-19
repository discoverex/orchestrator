from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import request


def _storage_base_url() -> str:
    base = os.getenv("STORAGE_API_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("missing required environment variable: STORAGE_API_URL")
    return base if base.endswith("/artifact") else f"{base}/artifact"


def upload_artifact_file(
    *,
    flow_run_id: str,
    attempt: int,
    filename: str,
    local_path: str | Path,
    content_type: str = "application/octet-stream",
) -> str:
    path = Path(local_path)
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"artifact file not found: {path}")

    body = path.read_bytes()
    req = request.Request(
        f"{_storage_base_url()}/v1/upload/file",
        method="PUT",
        data=body,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "X-Orch-Flow-Run-Id": flow_run_id,
            "X-Orch-Attempt": str(attempt),
            "X-Orch-Filename": filename,
        },
    )
    with request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw or "{}")
    object_uri = str(parsed.get("object_uri", "")).strip()
    if not object_uri:
        raise RuntimeError("upload response missing object_uri")
    return object_uri
