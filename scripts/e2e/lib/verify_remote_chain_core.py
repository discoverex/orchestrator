from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib import error, request


@dataclass
class VerifyError(Exception):
    step: str
    code: str
    message: str

    def as_json(self) -> dict[str, Any]:
        return {
            "ok": False,
            "step": self.step,
            "error_code": self.code,
            "error_message": self.message,
        }


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any] | list[dict[str, Any]]:
    body = None
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "orchestrator-e2e/1.0",
    }
    if headers:
        req_headers.update(headers)
    if payload is not None:
        req_headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(url, method=method, data=body, headers=req_headers)
    try:
        with request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - caller-controlled endpoint
            raw = resp.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VerifyError(
            "http", f"HTTP_{exc.code}", f"{method} {url} failed: {detail}"
        ) from exc
    except error.URLError as exc:
        raise VerifyError(
            "http", "HTTP_UNREACHABLE", f"{method} {url} unreachable: {exc.reason}"
        ) from exc
    if not raw:
        return {}
    parsed = json.loads(raw.decode("utf-8"))
    if isinstance(parsed, dict):
        return cast(dict[str, Any], parsed)
    if isinstance(parsed, list):
        rows = [row for row in parsed if isinstance(row, dict)]
        return cast(list[dict[str, Any]], rows)
    raise VerifyError(
        "http", "HTTP_BAD_JSON", f"{method} {url} returned non-object JSON"
    )


def gateway_headers(token: str) -> dict[str, str]:
    return {"Content-Type": "application/json"}


def run_ops_script(
    script_rel_path: str, env_overrides: dict[str, str], argv: list[str]
) -> dict[str, Any]:
    script_path = Path(__file__).resolve().parents[2] / "ops" / script_rel_path
    if shutil.which("uv"):
        cmd = ["uv", "run", "python", str(script_path), *argv]
    else:
        cmd = [sys.executable, str(script_path), *argv]
    env = os.environ.copy()
    env.update(env_overrides)
    proc = subprocess.run(cmd, check=False, text=True, capture_output=True, env=env)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        raise VerifyError(
            "ops-script", "SCRIPT_FAILED", f"{script_rel_path} failed: {detail}"
        )
    stdout = proc.stdout.strip()
    if not stdout:
        return {}
    parsed = json.loads(stdout)
    if not isinstance(parsed, dict):
        raise VerifyError(
            "ops-script",
            "SCRIPT_BAD_JSON",
            f"{script_rel_path} returned non-object JSON",
        )
    return cast(dict[str, Any], parsed)


def command_wait_completed(
    args: Any, http_json_fn: Callable[..., Any]
) -> dict[str, Any]:
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
    deadline = time.time() + args.timeout_sec
    last_state = "UNKNOWN"

    while time.time() < deadline:
        out = http_json_fn(
            "GET",
            f"{args.prefect_api_url.rstrip('/')}/flow_runs/{args.flow_run_id}",
            headers=headers,
        )
        if not isinstance(out, dict):
            raise VerifyError(
                "prefect-wait-completed",
                "PREFECT_BAD_RESPONSE",
                "expected dict response",
            )
        state_type = (
            out.get("state_type") or out.get("state", {}).get("type") or ""
        ).upper()
        last_state = state_type or "UNKNOWN"
        if state_type == "COMPLETED":
            return {
                "ok": True,
                "step": "prefect-wait-completed",
                "flow_run_id": args.flow_run_id,
                "state": state_type,
            }
        if state_type in {"FAILED", "CRASHED", "CANCELLED"}:
            raise VerifyError(
                "prefect-wait-completed",
                "FLOW_TERMINAL_FAILURE",
                f"flow run entered terminal failure state: {state_type}",
            )
        time.sleep(args.poll_interval_sec)

    raise VerifyError(
        "prefect-wait-completed",
        "FLOW_TIMEOUT",
        f"timed out waiting for completion (last_state={last_state}, timeout_sec={args.timeout_sec})",
    )


def command_storage_objects(
    args: Any, http_json_fn: Callable[..., Any]
) -> dict[str, Any]:
    attempt = args.attempt
    uris = {
        "stdout": f"s3://{args.artifact_bucket}/jobs/{args.flow_run_id}/attempt-{attempt}/stdout.log",
        "stderr": f"s3://{args.artifact_bucket}/jobs/{args.flow_run_id}/attempt-{attempt}/stderr.log",
        "result": f"s3://{args.artifact_bucket}/jobs/{args.flow_run_id}/attempt-{attempt}/result.json",
        "manifest": f"s3://{args.artifact_bucket}/jobs/{args.flow_run_id}/attempt-{attempt}/artifacts.json",
    }
    headers = gateway_headers("")
    cf_id = getattr(args, "prefect_cf_access_client_id", "") or getattr(
        args, "cf_access_client_id", ""
    )
    cf_secret = getattr(args, "prefect_cf_access_client_secret", "") or getattr(
        args, "cf_access_client_secret", ""
    )
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    base = args.storage_api_url.rstrip("/")

    for object_uri in uris.values():
        out = http_json_fn(
            "POST",
            f"{base}/v1/object/head",
            payload={"object_uri": object_uri},
            headers=headers,
        )
        if not isinstance(out, dict) or not out.get("exists"):
            raise VerifyError(
                "storage-objects", "OBJECT_MISSING", f"missing object: {object_uri}"
            )

    presign = http_json_fn(
        "POST",
        f"{base}/v1/presign/get",
        payload={
            "flow_run_id": args.flow_run_id,
            "attempt": attempt,
            "kind": "manifest",
            "filename": "artifacts.json",
        },
        headers=headers,
    )
    if not isinstance(presign, dict) or "url" not in presign:
        raise VerifyError(
            "storage-objects", "PRESIGN_FAILED", "invalid presign/get response"
        )

    manifest_raw = http_json_fn("GET", str(presign["url"]), timeout=60)
    if not isinstance(manifest_raw, dict):
        raise VerifyError(
            "storage-objects", "MANIFEST_BAD_TYPE", "manifest is not an object"
        )
    if manifest_raw.get("flow_run_id") != args.flow_run_id:
        raise VerifyError(
            "storage-objects",
            "MANIFEST_FLOW_RUN_ID_MISMATCH",
            "manifest flow_run_id mismatch",
        )
    if int(manifest_raw.get("attempt", -1)) != attempt:
        raise VerifyError(
            "storage-objects", "MANIFEST_ATTEMPT_MISMATCH", "manifest attempt mismatch"
        )

    artifacts = manifest_raw.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise VerifyError(
            "storage-objects",
            "MANIFEST_ARTIFACTS_BAD_TYPE",
            "manifest artifacts must be list",
        )
    by_kind = {
        row.get("kind"): row.get("object_uri")
        for row in artifacts
        if isinstance(row, dict)
    }
    for kind in ("stdout", "stderr", "result"):
        if by_kind.get(kind) != uris[kind]:
            raise VerifyError(
                "storage-objects",
                "MANIFEST_URI_MISMATCH",
                f"manifest mismatch for {kind}",
            )

    output = {
        "ok": True,
        "step": "storage-objects",
        "flow_run_id": args.flow_run_id,
        "attempt": attempt,
        "uris": uris,
    }
    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(output, ensure_ascii=True, indent=2), encoding="utf-8"
        )
    return output


def command_flush_verify(
    args: Any, run_ops_script_fn: Callable[..., Any]
) -> dict[str, Any]:
    env = {
        "PREFECT_API_URL": args.prefect_api_url,
        "FLUSH_TARGET_URL": args.storage_api_url,
        "FLUSH_CURSOR_PATH": args.cursor_path,
        "FLUSH_PAGE_SIZE": str(args.page_size),
        "FLUSH_MAX_RUNS": str(args.max_runs),
    }
    if args.prefect_cf_access_client_id and args.prefect_cf_access_client_secret:
        env["CF_ACCESS_CLIENT_ID"] = args.prefect_cf_access_client_id
        env["CF_ACCESS_CLIENT_SECRET"] = args.prefect_cf_access_client_secret
    payload = run_ops_script_fn(
        "prefect_flush_completed.py",
        env,
        [
            "--once",
            "--cursor-path",
            args.cursor_path,
            "--page-size",
            str(args.page_size),
            "--max-runs",
            str(args.max_runs),
        ],
    )
    uploaded = payload.get("uploaded", []) if isinstance(payload, dict) else []
    if not isinstance(uploaded, list):
        raise VerifyError(
            "flush-verify", "FLUSH_BAD_RESPONSE", "flush uploaded field must be list"
        )
    if not any(
        isinstance(row, dict) and row.get("flow_run_id") == args.flow_run_id
        for row in uploaded
    ):
        raise VerifyError(
            "flush-verify",
            "FLUSH_RUN_NOT_EXPORTED",
            "flush did not export target flow run",
        )
    return {
        "ok": True,
        "step": "flush-verify",
        "flow_run_id": args.flow_run_id,
        "uploaded_count": len(uploaded),
    }


def command_prune_verify(
    args: Any, run_ops_script_fn: Callable[..., Any], http_json_fn: Callable[..., Any]
) -> dict[str, Any]:
    env = {"PREFECT_API_URL": args.prefect_api_url}
    headers: dict[str, str] = {}
    if args.prefect_cf_access_client_id and args.prefect_cf_access_client_secret:
        env["CF_ACCESS_CLIENT_ID"] = args.prefect_cf_access_client_id
        env["CF_ACCESS_CLIENT_SECRET"] = args.prefect_cf_access_client_secret
        headers["CF-Access-Client-Id"] = args.prefect_cf_access_client_id
        headers["CF-Access-Client-Secret"] = args.prefect_cf_access_client_secret
    argv = [
        "--ttl-hours",
        str(args.ttl_hours),
        "--page-size",
        str(args.page_size),
        "--max-runs",
        str(args.max_runs),
    ]
    if args.apply:
        argv.insert(0, "--apply")
    payload = run_ops_script_fn("prefect_prune_completed.py", env, argv)

    if args.apply:
        try:
            out = http_json_fn(
                "GET",
                f"{args.prefect_api_url.rstrip('/')}/flow_runs/{args.flow_run_id}",
                headers=headers,
            )
            if not isinstance(out, dict):
                raise VerifyError(
                    "prune-verify", "PREFECT_BAD_RESPONSE", "expected dict response"
                )
        except VerifyError as exc:
            if exc.code == "HTTP_404":
                return {
                    "ok": True,
                    "step": "prune-verify",
                    "flow_run_id": args.flow_run_id,
                    "apply": True,
                    "deleted": payload.get("deleted", 0)
                    if isinstance(payload, dict)
                    else 0,
                }
            raise
        raise VerifyError(
            "prune-verify",
            "PRUNE_NOT_DELETED",
            "flow run still exists after apply prune",
        )

    return {
        "ok": True,
        "step": "prune-verify",
        "flow_run_id": args.flow_run_id,
        "apply": False,
        "payload": payload,
    }
