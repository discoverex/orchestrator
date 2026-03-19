from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Protocol

from storage.composition.container import build_storage_app_from_env
from storage.domain.models.object_ref import ObjectRef

logger = logging.getLogger("worker_artifacts")

STAGING_DIRNAME = "engine-artifacts"
READY_MARKER = "_UPLOAD_READY"
UPLOADED_MARKER = ".uploaded.json"
MANIFEST_OBJECT_NAME = "engine-artifacts.json"


class UploadService(Protocol):
    def upload_bytes(
        self,
        *,
        flow_run_id: str,
        attempt: int,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> ObjectRef: ...


def staging_root(runtime_root: str | Path) -> Path:
    return Path(runtime_root) / STAGING_DIRNAME


def run_forever() -> None:
    runtime_root = os.getenv("ORCH_WORKER_RUNTIME_DIR", "/var/lib/orchestrator")
    poll_interval = float(os.getenv("WORKER_ARTIFACT_SWEEP_INTERVAL_SEC", "5"))
    service = build_storage_app_from_env()
    root = staging_root(runtime_root)
    root.mkdir(parents=True, exist_ok=True)
    logger.info("artifact uploader started", extra={"staging_root": str(root)})
    while True:
        try:
            run_once(root=root, service=service)
        except Exception:
            logger.exception("artifact uploader sweep failed")
        time.sleep(poll_interval)


def run_once(*, root: Path, service: UploadService) -> int:
    uploaded_count = 0
    root.mkdir(parents=True, exist_ok=True)
    for flow_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if _upload_if_ready(flow_dir=flow_dir, service=service):
            uploaded_count += 1
    return uploaded_count


def _upload_if_ready(*, flow_dir: Path, service: UploadService) -> bool:
    ready_marker = flow_dir / READY_MARKER
    uploaded_marker = flow_dir / UPLOADED_MARKER
    if not ready_marker.exists() or uploaded_marker.exists():
        return False

    flow_run_id = flow_dir.name.strip()
    if not flow_run_id:
        logger.warning("skipping empty flow artifact directory name")
        return False

    object_uris: dict[str, str] = {}
    for file_path in sorted(_iter_payload_files(flow_dir)):
        relative_path = file_path.relative_to(flow_dir).as_posix()
        uploaded = service.upload_bytes(
            flow_run_id=flow_run_id,
            attempt=1,
            filename=f"engine/{relative_path}",
            data=file_path.read_bytes(),
            content_type=_content_type_for(file_path),
        )
        object_uris[relative_path] = uploaded.uri

    manifest_payload = {
        "flow_run_id": flow_run_id,
        "attempt": 1,
        "artifacts": [
            {"relative_path": relative_path, "object_uri": object_uri}
            for relative_path, object_uri in object_uris.items()
        ],
    }
    manifest_uploaded = service.upload_bytes(
        flow_run_id=flow_run_id,
        attempt=1,
        filename=MANIFEST_OBJECT_NAME,
        data=json.dumps(manifest_payload, ensure_ascii=True, indent=2).encode("utf-8"),
        content_type="application/json",
    )
    uploaded_marker.write_text(
        json.dumps(
            {
                "flow_run_id": flow_run_id,
                "attempt": 1,
                "manifest_uri": manifest_uploaded.uri,
                "artifacts": object_uris,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(
        "uploaded staged engine artifacts",
        extra={
            "flow_run_id": flow_run_id,
            "artifact_count": len(object_uris),
            "manifest_uri": manifest_uploaded.uri,
        },
    )
    return True


def _iter_payload_files(flow_dir: Path) -> list[Path]:
    return [
        path
        for path in flow_dir.rglob("*")
        if path.is_file() and path.name not in {READY_MARKER, UPLOADED_MARKER}
    ]


def _content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix in {".txt", ".log"}:
        return "text/plain"
    return "application/octet-stream"
