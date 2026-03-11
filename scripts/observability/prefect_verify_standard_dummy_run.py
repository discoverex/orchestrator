#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlsplit

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.observability.lib.prefect_observe import (  # noqa: E402
    ObserveError,
    bootstrap_env,
    print_json,
)


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "orchestrator-observability/1.0",
    }
    cf_id = os.getenv("CF_ACCESS_CLIENT_ID", "").strip()
    cf_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 30,
) -> Any:
    body = None
    headers = _headers()
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(url, method=method, data=body, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            raw = resp.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ObserveError(f"{method} {url} failed: HTTP {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise ObserveError(f"{method} {url} unreachable: {exc.reason}") from exc
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _storage_head(storage_api_url: str, object_uri: str) -> dict[str, Any]:
    payload = _request_json(
        "POST",
        f"{storage_api_url.rstrip('/')}/artifact/v1/object/head",
        {"object_uri": object_uri},
    )
    if not isinstance(payload, dict):
        raise ObserveError("unexpected storage head response shape")
    return payload


def _verify_storage(storage_api_url: str, flow_run_id: str, attempt: int) -> dict[str, Any]:
    keys = {
        "stdout": f"s3://orchestrator-artifacts/jobs/{flow_run_id}/attempt-{attempt}/stdout.log",
        "stderr": f"s3://orchestrator-artifacts/jobs/{flow_run_id}/attempt-{attempt}/stderr.log",
        "result": f"s3://orchestrator-artifacts/jobs/{flow_run_id}/attempt-{attempt}/result.json",
        "manifest": f"s3://orchestrator-artifacts/jobs/{flow_run_id}/attempt-{attempt}/artifacts.json",
    }
    out: dict[str, Any] = {}
    for kind, uri in keys.items():
        row = _storage_head(storage_api_url, uri)
        out[kind] = {
            "object_uri": uri,
            "exists": bool(row.get("exists")),
            "size": row.get("size"),
        }
    return out


def _verify_mlflow(tracking_uri: str, flow_run_id: str) -> dict[str, Any]:
    payload = _request_json(
        "POST",
        f"{tracking_uri.rstrip('/')}/api/2.0/mlflow/runs/search",
        {
            "experiment_ids": ["0"],
            "filter": (
                f"tags.e2e_flow_run_id = '{flow_run_id}' "
                "and tags.e2e_dummy = 'standard'"
            ),
            "max_results": 5,
            "order_by": ["attributes.start_time DESC"],
        },
    )
    if not isinstance(payload, dict):
        raise ObserveError("unexpected mlflow runs/search response shape")
    rows = payload.get("runs", [])
    if not isinstance(rows, list) or not rows:
        raise ObserveError(f"no matching MLflow run found for flow_run_id={flow_run_id}")
    row = rows[0]
    if not isinstance(row, dict):
        raise ObserveError("unexpected mlflow run row shape")
    info = row.get("info", {})
    data = row.get("data", {})
    tags = {}
    if isinstance(data, dict):
        raw_tags = data.get("tags", [])
        if isinstance(raw_tags, list):
            tags = {
                str(tag.get("key")): str(tag.get("value"))
                for tag in raw_tags
                if isinstance(tag, dict) and "key" in tag and "value" in tag
            }
    return {
        "run_id": info.get("run_id") if isinstance(info, dict) else None,
        "status": info.get("status") if isinstance(info, dict) else None,
        "experiment_id": info.get("experiment_id") if isinstance(info, dict) else None,
        "tags": tags,
    }


def _has_mlflow_path(uri: str) -> bool:
    return "/mlflow" in urlsplit(uri).path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify standard dummy flow artifacts and MLflow run."
    )
    parser.add_argument("--flow-run-id", required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--storage-api-url", default="")
    parser.add_argument("--mlflow-tracking-uri", default="")
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    bootstrap_env(args.env_file)
    storage_api_url = args.storage_api_url.strip() or os.getenv("STORAGE_API_URL", "").strip()
    if not storage_api_url:
        raise ObserveError("missing STORAGE_API_URL")
    tracking_uri = args.mlflow_tracking_uri.strip()
    if not tracking_uri:
        tracking_uri = f"{storage_api_url.rstrip('/')}/mlflow"
    env_tracking_uri = os.getenv("ENGINE_MLFLOW_TRACKING_URI", "").strip()
    if not args.mlflow_tracking_uri and _has_mlflow_path(env_tracking_uri):
        tracking_uri = env_tracking_uri
    env_tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    if not args.mlflow_tracking_uri and _has_mlflow_path(env_tracking_uri):
        tracking_uri = env_tracking_uri

    storage = _verify_storage(storage_api_url, args.flow_run_id, args.attempt)
    mlflow = _verify_mlflow(tracking_uri, args.flow_run_id)
    result = {
        "flow_run_id": args.flow_run_id,
        "attempt": args.attempt,
        "storage": storage,
        "mlflow": mlflow,
    }
    print_json(result)
    if not all(bool(row["exists"]) for row in storage.values()):
        return 1
    if str(mlflow["tags"].get("e2e_flow_run_id", "")) != args.flow_run_id:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
