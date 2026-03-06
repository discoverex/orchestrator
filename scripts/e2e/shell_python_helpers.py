#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib import error, parse, request
from urllib.parse import urlsplit


def _read_steps(steps_file: Path) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    if not steps_file.exists():
        return steps
    for raw in steps_file.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        name, status, message = raw.split("\t", 2)
        steps.append({"name": name, "status": status, "message": message})
    return steps


def cmd_write_summary_local(args: argparse.Namespace) -> int:
    steps = _read_steps(Path(args.steps_file))
    summary = {
        "mode": args.mode,
        "ok": all(step["status"] == "pass" for step in steps),
        "flow_run_id": args.flow_run_id or None,
        "mlflow_run_id": args.mlflow_run_id or None,
        "steps": steps,
    }
    summary_file = Path(args.summary_file)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    return 0


def _http_json(method: str, url: str, *, payload: dict | None = None, headers: dict[str, str] | None = None, timeout: int = 15) -> dict:
    data = None
    req_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = request.Request(url, method=method, data=data, headers=req_headers)
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cmd_poll_prefect_completion(args: argparse.Namespace) -> int:
    api_url = args.prefect_api_url.rstrip("/")
    terminal_success = {"COMPLETED"}
    terminal_fail = {"FAILED", "CRASHED", "CANCELLED"}

    deadline = time.time() + args.timeout_sec
    while time.time() < deadline:
        payload = _http_json("GET", f"{api_url}/flow_runs/{args.flow_run_id}", timeout=10)
        state_type = (payload.get("state_type") or payload.get("state", {}).get("type") or "").upper()
        if state_type in terminal_success:
            print("COMPLETED")
            return 0
        if state_type in terminal_fail:
            print(state_type)
            return 2
        time.sleep(2)

    print("TIMEOUT")
    return 3


def cmd_verify_storage_objects(args: argparse.Namespace) -> int:
    flow_run_id = args.flow_run_id
    gateway = args.storage_gateway_url.rstrip("/")
    token = args.storage_gateway_token
    bucket = args.artifact_bucket
    log_dir = Path(args.log_dir)
    attempt = 1

    uris = {
        "stdout": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/stdout.log",
        "stderr": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/stderr.log",
        "result": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/result.json",
        "manifest": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/artifacts.json",
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    for object_uri in uris.values():
        payload = _http_json(
            "POST",
            f"{gateway}/v1/object/head",
            payload={"object_uri": object_uri},
            headers=headers,
            timeout=10,
        )
        if not payload.get("exists"):
            raise SystemExit(f"missing object: {object_uri}")

    manifest_link = _http_json(
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

    req = request.Request(manifest_link["url"], method="GET")
    with request.urlopen(req, timeout=15) as resp:
        manifest = json.loads(resp.read().decode("utf-8"))

    if manifest.get("flow_run_id") != flow_run_id:
        raise SystemExit("manifest flow_run_id mismatch")
    if int(manifest.get("attempt", -1)) != attempt:
        raise SystemExit("manifest attempt mismatch")

    rows = manifest.get("artifacts", [])
    kinds = {row.get("kind"): row.get("object_uri") for row in rows if isinstance(row, dict)}
    for kind in ("stdout", "stderr", "result"):
        if kinds.get(kind) != uris[kind]:
            raise SystemExit(f"manifest {kind} uri mismatch")

    (log_dir / "flow_uris.json").write_text(json.dumps(uris, ensure_ascii=True, indent=2), encoding="utf-8")
    return 0


def cmd_create_and_verify_mlflow_tags(args: argparse.Namespace) -> int:
    tracking_uri = args.mlflow_tracking_uri.rstrip("/")
    flow_run_id = args.flow_run_id
    log_dir = Path(args.log_dir)
    cf_access_client_id = args.cf_access_client_id or ""
    cf_access_client_secret = args.cf_access_client_secret or ""
    flow_uris = json.loads((log_dir / "flow_uris.json").read_text(encoding="utf-8"))

    base_headers = {
        "Content-Type": "application/json",
        "User-Agent": "orchestrator-e2e/1.0",
    }
    if cf_access_client_id and cf_access_client_secret:
        base_headers["CF-Access-Client-Id"] = cf_access_client_id
        base_headers["CF-Access-Client-Secret"] = cf_access_client_secret

    def post(path: str, payload: dict) -> dict:
        return _http_json("POST", f"{tracking_uri}{path}", payload=payload, headers=base_headers, timeout=15)

    def get(path: str, query: dict) -> dict:
        qs = parse.urlencode(query)
        return _http_json("GET", f"{tracking_uri}{path}?{qs}", headers=base_headers, timeout=15)

    experiment_id = "0"
    try:
        run = post("/api/2.0/mlflow/runs/create", {"experiment_id": experiment_id, "start_time": 0, "tags": []})
    except error.HTTPError as exc:
        raise SystemExit(f"mlflow runs/create failed: HTTP {exc.code}") from exc

    run_id = run["run"]["info"]["run_id"]
    tags = {
        "artifact_manifest_uri": flow_uris["manifest"],
        "artifact_stdout_uri": flow_uris["stdout"],
        "artifact_stderr_uri": flow_uris["stderr"],
        "artifact_result_uri": flow_uris["result"],
        "e2e_flow_run_id": flow_run_id,
    }
    for key, value in tags.items():
        post("/api/2.0/mlflow/runs/set-tag", {"run_id": run_id, "key": key, "value": value})

    fetched = get("/api/2.0/mlflow/runs/get", {"run_id": run_id})
    rows = fetched["run"]["data"].get("tags", [])
    values = {row["key"]: row["value"] for row in rows}
    for key, value in tags.items():
        if values.get(key) != value:
            raise SystemExit(f"mlflow tag mismatch: {key}")

    print(run_id)
    return 0


def cmd_uri_host(args: argparse.Namespace) -> int:
    host = urlsplit(args.uri).hostname or ""
    if not host:
        raise SystemExit("unable to parse host from uri")
    print(host)
    return 0


def cmd_verify_flush_output(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.output_json).read_text(encoding="utf-8"))
    uploaded = payload.get("uploaded", [])
    if not any(row.get("flow_run_id") == args.flow_run_id for row in uploaded):
        raise SystemExit("flush did not export current flow run")
    print("flush-ok")
    return 0


def cmd_verify_prune_removed(args: argparse.Namespace) -> int:
    api_url = args.prefect_api_url.rstrip("/")
    req = request.Request(f"{api_url}/flow_runs/{args.flow_run_id}", method="GET")
    try:
        with request.urlopen(req, timeout=10):
            raise SystemExit("flow run still exists after prune")
    except error.HTTPError as exc:
        if exc.code != 404:
            raise
    print("prune-ok")
    return 0


def cmd_write_summary_remote(args: argparse.Namespace) -> int:
    steps = _read_steps(Path(args.steps_file))
    summary = {
        "ok": all(step["status"] == "pass" for step in steps),
        "flow_run_id": args.flow_run_id or None,
        "prefect_api_url": args.prefect_api_url,
        "work_pool": args.work_pool,
        "work_queue": args.work_queue,
        "prune_mode": args.prune_mode,
        "steps": steps,
    }
    summary_file = Path(args.summary_file)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    return 0


def cmd_build_cf_headers_json(args: argparse.Namespace) -> int:
    print(
        json.dumps(
            {
                "CF-Access-Client-Id": args.client_id,
                "CF-Access-Client-Secret": args.client_secret,
            },
            ensure_ascii=True,
        )
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shell helper commands used by e2e scripts.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("write-summary-local")
    p.add_argument("--steps-file", required=True)
    p.add_argument("--summary-file", required=True)
    p.add_argument("--mode", required=True)
    p.add_argument("--flow-run-id", default="")
    p.add_argument("--mlflow-run-id", default="")
    p.set_defaults(func=cmd_write_summary_local)

    p = sub.add_parser("poll-prefect-completion")
    p.add_argument("--prefect-api-url", required=True)
    p.add_argument("--flow-run-id", required=True)
    p.add_argument("--timeout-sec", required=True, type=int)
    p.set_defaults(func=cmd_poll_prefect_completion)

    p = sub.add_parser("verify-storage-objects")
    p.add_argument("--flow-run-id", required=True)
    p.add_argument("--storage-gateway-url", required=True)
    p.add_argument("--storage-gateway-token", required=True)
    p.add_argument("--artifact-bucket", required=True)
    p.add_argument("--log-dir", required=True)
    p.set_defaults(func=cmd_verify_storage_objects)

    p = sub.add_parser("create-and-verify-mlflow-tags")
    p.add_argument("--mlflow-tracking-uri", required=True)
    p.add_argument("--flow-run-id", required=True)
    p.add_argument("--log-dir", required=True)
    p.add_argument("--cf-access-client-id", default="")
    p.add_argument("--cf-access-client-secret", default="")
    p.set_defaults(func=cmd_create_and_verify_mlflow_tags)

    p = sub.add_parser("uri-host")
    p.add_argument("--uri", required=True)
    p.set_defaults(func=cmd_uri_host)

    p = sub.add_parser("verify-flush-output")
    p.add_argument("--output-json", required=True)
    p.add_argument("--flow-run-id", required=True)
    p.set_defaults(func=cmd_verify_flush_output)

    p = sub.add_parser("verify-prune-removed")
    p.add_argument("--prefect-api-url", required=True)
    p.add_argument("--flow-run-id", required=True)
    p.set_defaults(func=cmd_verify_prune_removed)

    p = sub.add_parser("write-summary-remote")
    p.add_argument("--steps-file", required=True)
    p.add_argument("--summary-file", required=True)
    p.add_argument("--flow-run-id", default="")
    p.add_argument("--prefect-api-url", required=True)
    p.add_argument("--work-pool", required=True)
    p.add_argument("--work-queue", required=True)
    p.add_argument("--prune-mode", required=True)
    p.set_defaults(func=cmd_write_summary_remote)

    p = sub.add_parser("build-cf-headers-json")
    p.add_argument("--client-id", required=True)
    p.add_argument("--client-secret", required=True)
    p.set_defaults(func=cmd_build_cf_headers_json)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
