from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .errors import VerifyError
from .utils import artifact_api_base


def _cf_headers(args: argparse.Namespace) -> dict[str, str]:
    headers: dict[str, str] = {}
    cf_id = getattr(args, "prefect_cf_access_client_id", "") or getattr(
        args, "cf_access_client_id", ""
    )
    cf_secret = getattr(args, "prefect_cf_access_client_secret", "") or getattr(
        args, "cf_access_client_secret", ""
    )
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def command_wait_completed(
    args: argparse.Namespace,
    http_json_fn: Callable[..., Any],
) -> dict[str, Any]:
    api_url = args.prefect_api_url.rstrip("/")
    headers = _cf_headers(args)
    deadline = time.time() + args.timeout_sec
    while time.time() < deadline:
        payload = http_json_fn(
            "GET",
            f"{api_url}/flow_runs/{args.flow_run_id}",
            headers=headers,
            timeout=10,
        )
        state_type = str(payload.get("state_type") or "").upper()
        if state_type == "COMPLETED":
            return {"ok": True, "step": "prefect-wait", "state": state_type}
        if state_type in {"FAILED", "CRASHED", "CANCELLED"}:
            raise VerifyError(
                "prefect-wait", f"STATE_{state_type}", f"flow run {state_type}"
            )
        time.sleep(args.poll_interval_sec)
    raise VerifyError("prefect-wait", "TIMEOUT", "flow run timed out")


def command_storage_objects(
    args: argparse.Namespace,
    http_json_fn: Callable[..., Any],
) -> dict[str, Any]:
    gateway = artifact_api_base(args.storage_api_url)
    headers = _cf_headers(args)
    uris = {
        "stdout": f"s3://{args.artifact_bucket}/jobs/{args.flow_run_id}/attempt-{args.attempt}/stdout.log",
        "stderr": f"s3://{args.artifact_bucket}/jobs/{args.flow_run_id}/attempt-{args.attempt}/stderr.log",
        "result": f"s3://{args.artifact_bucket}/jobs/{args.flow_run_id}/attempt-{args.attempt}/result.json",
        "manifest": f"s3://{args.artifact_bucket}/jobs/{args.flow_run_id}/attempt-{args.attempt}/artifacts.json",
    }
    for key, object_uri in uris.items():
        payload = http_json_fn(
            "POST",
            f"{gateway}/v1/object/head",
            payload={"object_uri": object_uri},
            headers=headers,
            timeout=10,
        )
        if not payload.get("exists"):
            raise VerifyError(
                "storage-objects", f"MISSING_{key.upper()}", f"missing {object_uri}"
            )
    res = {"ok": True, "step": "storage-objects", "uris": uris}
    if getattr(args, "output_json", None):
        import json

        Path(args.output_json).write_text(
            json.dumps(res, ensure_ascii=True), encoding="utf-8"
        )
    return res


def command_flush_verify(
    args: argparse.Namespace,
    run_ops_fn: Callable[..., Any],
) -> dict[str, Any]:
    env = {
        "PREFECT_API_URL": args.prefect_api_url,
        "CF_ACCESS_CLIENT_ID": getattr(args, "prefect_cf_access_client_id", "") or "",
        "CF_ACCESS_CLIENT_SECRET": getattr(args, "prefect_cf_access_client_secret", "")
        or "",
        "FLUSH_TARGET_URL": f"{args.storage_api_url.rstrip('/')}/artifact",
        "FLUSH_CURSOR_PATH": args.cursor_path,
    }
    payload = run_ops_fn(
        "prefect_flush_completed.py",
        env,
        [
            "--once",
            "--page-size",
            str(args.page_size),
            "--max-runs",
            str(args.max_runs),
        ],
    )
    uploaded = payload.get("uploaded", [])
    if not any(row.get("flow_run_id") == args.flow_run_id for row in uploaded):
        raise VerifyError(
            "flush-verify", "NOT_EXPORTED", "flow run not in flush output"
        )
    return {"ok": True, "step": "flush-verify", "flow_run_id": args.flow_run_id}


def command_prune_verify(
    args: argparse.Namespace,
    run_ops_fn: Callable[..., Any],
    http_json_fn: Callable[..., Any],
) -> dict[str, Any]:
    env = {
        "PREFECT_API_URL": args.prefect_api_url,
        "CF_ACCESS_CLIENT_ID": getattr(args, "prefect_cf_access_client_id", "") or "",
        "CF_ACCESS_CLIENT_SECRET": getattr(args, "prefect_cf_access_client_secret", "")
        or "",
    }
    argv = [
        "--ttl-hours",
        str(args.ttl_hours),
        "--page-size",
        str(args.page_size),
        "--max-runs",
        str(args.max_runs),
    ]
    if args.apply:
        argv.append("--apply")
    run_ops_fn("prefect_prune_completed.py", env, argv)

    if args.apply:
        try:
            http_json_fn(
                "GET",
                f"{args.prefect_api_url.rstrip('/')}/flow_runs/{args.flow_run_id}",
                headers=_cf_headers(args),
            )
            raise VerifyError(
                "prune-verify", "STILL_EXISTS", "flow run exists after apply prune"
            )
        except VerifyError as exc:
            if "HTTP_404" not in exc.code:
                raise
    return {
        "ok": True,
        "step": "prune-verify",
        "flow_run_id": args.flow_run_id,
        "apply": args.apply,
    }
