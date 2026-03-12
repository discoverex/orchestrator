from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from flows.engine_run.models import ArtifactLink


def prepare_manifest_links(
    *,
    flow_run_id: str,
    attempt: int,
    gateway: str,
    http_json: Callable[[str, str, dict[str, object]], object],
    logger: logging.Logger,
) -> list[ArtifactLink]:
    rows = http_json(
        "POST",
        f"{gateway}/v1/presign/batch",
        {
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
        },
    )
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
    *,
    links: list[ArtifactLink],
    local_paths: dict[str, str],
    flow_run_id: str,
    attempt: int,
    already_uploaded: dict[str, str] | None,
    upload_file: Callable[[str, bytes], None],
    logger: logging.Logger,
) -> dict[str, str]:
    output: dict[str, str] = dict(already_uploaded or {})
    for link in links:
        if link.kind in output:
            continue
        if link.kind == "manifest":
            _upload_manifest(
                link=link,
                local_paths=local_paths,
                flow_run_id=flow_run_id,
                attempt=attempt,
                uploaded=output,
                upload_file=upload_file,
                logger=logger,
            )
            continue
        src = Path(local_paths[link.kind])
        logger.info(
            "uploading artifact: kind=%s object_uri=%s url=%s local_path=%s",
            link.kind,
            link.object_uri,
            link.url,
            src,
        )
        upload_file(link.url, src.read_bytes())
        output[link.kind] = link.object_uri
    return output


def _upload_manifest(
    *,
    link: ArtifactLink,
    local_paths: dict[str, str],
    flow_run_id: str,
    attempt: int,
    uploaded: dict[str, str],
    upload_file: Callable[[str, bytes], None],
    logger: logging.Logger,
) -> None:
    manifest = {
        "flow_run_id": flow_run_id,
        "attempt": attempt,
        "artifacts": [
            {"kind": kind, "object_uri": uri}
            for kind, uri in uploaded.items()
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
    upload_file(link.url, manifest_path.read_bytes())
    uploaded["manifest"] = link.object_uri
