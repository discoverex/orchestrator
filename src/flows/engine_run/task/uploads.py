from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from flows.engine_run.models import ArtifactLink


def prepare_manifest_links(
    flow_run_id: str,
    attempt: int,
    *,
    logger: logging.Logger,
    http_json_fn: Callable[[str, str, dict[str, object]], object],
    storage_base_url_fn: Callable[[], str],
) -> list[ArtifactLink]:
    gateway = storage_base_url_fn()
    payload = {
        "flow_run_id": flow_run_id,
        "attempt": attempt,
        "entries": [
            {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "kind": "stdout",
                "filename": "stdout.log",
            },
            {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "kind": "stderr",
                "filename": "stderr.log",
            },
            {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "kind": "result",
                "filename": "result.json",
            },
            {
                "flow_run_id": flow_run_id,
                "attempt": attempt,
                "kind": "manifest",
                "filename": "artifacts.json",
            },
        ],
    }
    rows = http_json_fn("POST", f"{gateway}/v1/presign/batch", payload)
    assert isinstance(rows, list)
    links = [
        ArtifactLink(
            kind=str(row["kind"]),
            object_uri=str(row["object_uri"]),
            url=str(row["url"]),
        )
        for row in rows
    ]
    logger.info(
        "issued artifact links: %s",
        [
            {"kind": link.kind, "object_uri": link.object_uri, "url": link.url}
            for link in links
        ],
    )
    return links


def upload_outputs(
    links: list[ArtifactLink],
    local_paths: dict[str, str],
    flow_run_id: str,
    attempt: int,
    *,
    logger: logging.Logger,
    upload_file_fn: Callable[[str, bytes], None],
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
                "artifacts": [
                    {"kind": kind, "object_uri": uri}
                    for kind, uri in output.items()
                    if kind != "manifest"
                ],
            }
            manifest_path = Path(local_paths["result"]).parent / "artifacts.json"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
            logger.info(
                "uploading manifest artifact: kind=%s object_uri=%s url=%s",
                link.kind,
                link.object_uri,
                link.url,
            )
            upload_file_fn(link.url, manifest_path.read_bytes())
            output["manifest"] = link.object_uri
            continue

        src = Path(local_paths[link.kind])
        logger.info(
            "uploading artifact: kind=%s object_uri=%s url=%s local_path=%s",
            link.kind,
            link.object_uri,
            link.url,
            src,
        )
        upload_file_fn(link.url, src.read_bytes())
        output[link.kind] = link.object_uri
    return output
