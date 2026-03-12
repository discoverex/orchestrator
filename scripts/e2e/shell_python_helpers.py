#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from urllib import error, parse, request
from urllib.parse import urlsplit, urlunsplit


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
    summary_file.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return 0


def _http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict[str, object]:
    data = None
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "orchestrator-e2e/1.0",
    }
    if headers:
        req_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = request.Request(url, method=method, data=data, headers=req_headers)
    with request.urlopen(req, timeout=timeout) as resp:
        parsed = json.loads(resp.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise SystemExit(f"expected JSON object from {method} {url}")
    return cast(dict[str, object], parsed)


def _http_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> str:
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "orchestrator-e2e/1.0",
    }
    if headers:
        req_headers.update(headers)
    req = request.Request(url, method="GET", headers=req_headers)
    with request.urlopen(req, timeout=timeout) as resp:
        body = cast(bytes, resp.read())
    return body.decode("utf-8")


def _artifact_api_base(storage_api_url: str) -> str:
    base = storage_api_url.rstrip("/")
    if base.endswith("/artifact"):
        return base
    return f"{base}/artifact"


def _download_headers(presigned_host_header: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    if presigned_host_header:
        headers["Host"] = presigned_host_header
    return headers


def _rewrite_presigned_url(url: str, internal_base_url: str) -> str:
    if not internal_base_url:
        return url
    src = urlsplit(url)
    dst = urlsplit(internal_base_url)
    if not src.scheme or not src.netloc or not dst.scheme or not dst.netloc:
        return url
    host = (src.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost"}:
        return url
    return urlunsplit((dst.scheme, dst.netloc, src.path, src.query, src.fragment))


def _extract_json_object(raw: str) -> dict[str, object]:
    for line in reversed(raw.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return cast(dict[str, object], parsed)
    raise SystemExit("unable to extract JSON object from stdout")


def _find_mlflow_experiment_id(
    tracking_uri: str,
    experiment_name: str,
    headers: dict[str, str],
) -> str:
    try:
        experiment = _http_json(
            "GET",
            (
                f"{tracking_uri}/api/2.0/mlflow/experiments/get-by-name"
                f"?experiment_name={parse.quote(experiment_name, safe='')}"
            ),
            headers=headers,
            timeout=20,
        )
    except error.HTTPError as exc:
        if exc.code != 404:
            raise
    else:
        row = experiment.get("experiment", {})
        if isinstance(row, dict):
            experiment_id = str(row.get("experiment_id", "")).strip()
            if experiment_id:
                return experiment_id

    try:
        experiments = _http_json(
            "POST",
            f"{tracking_uri}/api/2.0/mlflow/experiments/search",
            payload={"filter": f"name = '{experiment_name}'", "max_results": 20},
            headers=headers,
            timeout=20,
        )
    except error.HTTPError as exc:
        if exc.code != 404:
            raise
    else:
        experiment_rows = experiments.get("experiments", [])
        if not isinstance(experiment_rows, list):
            raise SystemExit(
                "mlflow experiments/search returned invalid experiments list"
            )
        for row in experiment_rows:
            if isinstance(row, dict) and str(row.get("name", "")) == experiment_name:
                experiment_id = str(row.get("experiment_id", "")).strip()
                if experiment_id:
                    return experiment_id

    # Older/local MLflow builds may not expose search endpoints consistently.
    # Probe a bounded range of experiment ids to recover the named experiment.
    for candidate_id in range(0, 21):
        try:
            experiment = _http_json(
                "GET",
                (
                    f"{tracking_uri}/api/2.0/mlflow/experiments/get"
                    f"?experiment_id={candidate_id}"
                ),
                headers=headers,
                timeout=20,
            )
        except error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        row = experiment.get("experiment", {})
        if isinstance(row, dict) and str(row.get("name", "")) == experiment_name:
            experiment_id = str(row.get("experiment_id", "")).strip()
            if experiment_id:
                return experiment_id

    return ""


def _mlflow_run_matches_scene_version(
    run: dict[str, object],
    *,
    scene_id: str,
    version_id: str,
) -> bool:
    data = run.get("data", {})
    if not isinstance(data, dict):
        return False
    params_raw = data.get("params", [])
    if not isinstance(params_raw, list):
        return False
    values = {
        str(row.get("key", "")): str(row.get("value", ""))
        for row in params_raw
        if isinstance(row, dict)
    }
    return values.get("scene_id") == scene_id and values.get("version_id") == version_id


def cmd_poll_prefect_completion(args: argparse.Namespace) -> int:
    api_url = args.prefect_api_url.rstrip("/")
    terminal_success = {"COMPLETED"}
    terminal_fail = {"FAILED", "CRASHED", "CANCELLED"}
    transient_statuses = {403, 404, 429, 500, 502, 503, 504}

    deadline = time.time() + args.timeout_sec
    while time.time() < deadline:
        try:
            payload = cast(
                dict[str, Any],
                _http_json(
                    "GET", f"{api_url}/flow_runs/{args.flow_run_id}", timeout=10
                ),
            )
        except error.HTTPError as exc:
            if exc.code in transient_statuses:
                time.sleep(2)
                continue
            raise
        state_type_raw = payload.get("state_type")
        if not state_type_raw:
            state = payload.get("state")
            if isinstance(state, dict):
                state_type_raw = state.get("type")
        state_type = str(state_type_raw or "").upper()
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
    gateway = _artifact_api_base(args.storage_api_url)
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
        payload = _http_json(
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

    manifest_url = _rewrite_presigned_url(
        str(manifest_link.get("url", "")),
        args.presigned_internal_base_url,
    )
    download_headers = _download_headers(args.presigned_host_header)
    if args.cf_access_client_id and args.cf_access_client_secret:
        download_headers["CF-Access-Client-Id"] = args.cf_access_client_id
        download_headers["CF-Access-Client-Secret"] = args.cf_access_client_secret
    manifest = cast(
        dict[str, object],
        json.loads(_http_text(manifest_url, headers=download_headers, timeout=15)),
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

    stdout_link = _http_json(
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
    stdout_url = _rewrite_presigned_url(
        str(stdout_link.get("url", "")),
        args.presigned_internal_base_url,
    )
    result_link = _http_json(
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
    result_url = _rewrite_presigned_url(
        str(result_link.get("url", "")),
        args.presigned_internal_base_url,
    )
    result_payload = cast(
        dict[str, object],
        json.loads(_http_text(result_url, headers=download_headers, timeout=15)),
    )
    exit_code = int(str(result_payload.get("exit_code", -1)))
    if exit_code != 0:
        raise SystemExit(f"engine entrypoint exited with code {exit_code}")

    engine_output = _extract_json_object(
        _http_text(stdout_url, headers=download_headers, timeout=15)
    )
    scene_id = str(engine_output.get("scene_id", "")).strip()
    version_id = str(engine_output.get("version_id", "")).strip()
    (log_dir / "engine_output.json").write_text(
        json.dumps(engine_output, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    if not scene_id or not version_id:
        raise SystemExit("engine stdout missing scene_id/version_id")

    engine_uris = {
        "scene_json": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/engine/scene/scene.json",
        "verification_json": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/engine/scene/verification.json",
        "engine_manifest": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/engine-artifacts.json",
    }
    for object_uri in engine_uris.values():
        payload = _http_json(
            "POST",
            f"{gateway}/v1/object/head",
            payload={"object_uri": object_uri},
            headers=headers,
            timeout=10,
        )
        if not payload.get("exists"):
            raise SystemExit(f"missing engine object: {object_uri}")

    engine_manifest_link = _http_json(
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
    engine_manifest_url = _rewrite_presigned_url(
        str(engine_manifest_link.get("url", "")),
        args.presigned_internal_base_url,
    )
    engine_manifest = cast(
        dict[str, object],
        json.loads(
            _http_text(engine_manifest_url, headers=download_headers, timeout=15)
        ),
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
    return 0


def cmd_verify_engine_mlflow_run(args: argparse.Namespace) -> int:
    tracking_uri = args.mlflow_tracking_uri.rstrip("/")
    log_dir = Path(args.log_dir)
    engine_output = cast(
        dict[str, object],
        json.loads((log_dir / "engine_output.json").read_text(encoding="utf-8")),
    )
    scene_id = str(engine_output.get("scene_id", "")).strip()
    version_id = str(engine_output.get("version_id", "")).strip()
    if not scene_id or not version_id:
        raise SystemExit("engine output missing scene_id/version_id")

    headers = {"Content-Type": "application/json", "User-Agent": "orchestrator-e2e/1.0"}
    if args.cf_access_client_id and args.cf_access_client_secret:
        headers["CF-Access-Client-Id"] = args.cf_access_client_id
        headers["CF-Access-Client-Secret"] = args.cf_access_client_secret

    experiment_id = _find_mlflow_experiment_id(
        tracking_uri,
        "discoverex-core",
        headers,
    )
    candidate_ids: list[str] = []
    if experiment_id:
        candidate_ids.append(experiment_id)
    candidate_ids.extend(
        str(candidate_id)
        for candidate_id in range(0, 21)
        if str(candidate_id) != experiment_id
    )

    run_rows: list[dict[str, object]] = []
    for candidate_id in candidate_ids:
        try:
            runs = _http_json(
                "POST",
                f"{tracking_uri}/api/2.0/mlflow/runs/search",
                payload={
                    "experiment_ids": [candidate_id],
                    "max_results": 20,
                },
                headers=headers,
                timeout=20,
            )
        except error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        rows = runs.get("runs", [])
        if not isinstance(rows, list):
            raise SystemExit("mlflow runs/search returned invalid runs list")
        matched = [
            row
            for row in rows
            if isinstance(row, dict)
            and _mlflow_run_matches_scene_version(
                row,
                scene_id=scene_id,
                version_id=version_id,
            )
        ]
        if matched:
            run_rows = matched
            break
    if not run_rows:
        raise SystemExit("no matching MLflow run found for engine scene output")

    run = run_rows[0]
    if not isinstance(run, dict):
        raise SystemExit("mlflow runs/search returned invalid run row")
    run_info = run.get("info", {})
    if not isinstance(run_info, dict):
        raise SystemExit("mlflow run info missing")
    run_id = str(run_info.get("run_id", "")).strip()
    if not run_id:
        raise SystemExit("mlflow run_id missing")
    run_data = run.get("data", {})
    if not isinstance(run_data, dict):
        raise SystemExit("mlflow run data missing")
    tags = run_data.get("tags", [])
    if not isinstance(tags, list):
        raise SystemExit("mlflow run tags missing")
    values = {
        str(tag.get("key")): str(tag.get("value"))
        for tag in tags
        if isinstance(tag, dict) and "key" in tag and "value" in tag
    }
    engine_uris_path = log_dir / "engine_uris.json"
    if engine_uris_path.exists():
        engine_uris = cast(
            dict[str, str], json.loads(engine_uris_path.read_text(encoding="utf-8"))
        )
        expected_tags = {
            "artifact_engine_manifest_uri": engine_uris["engine_manifest"],
            "artifact_scene_uri": engine_uris["scene_json"],
            "artifact_verification_uri": engine_uris["verification_json"],
        }
        for key, value in expected_tags.items():
            if values.get(key) != value:
                raise SystemExit(f"mlflow worker tag mismatch: {key}")

    (log_dir / "mlflow_run.json").write_text(
        json.dumps(run, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    print(run_id)
    return 0


def cmd_create_and_verify_mlflow_tags(args: argparse.Namespace) -> int:
    tracking_uri = args.mlflow_tracking_uri.rstrip("/")
    flow_run_id = args.flow_run_id
    log_dir = Path(args.log_dir)
    cf_access_client_id = args.cf_access_client_id or ""
    cf_access_client_secret = args.cf_access_client_secret or ""
    flow_uris = cast(
        dict[str, str],
        json.loads((log_dir / "flow_uris.json").read_text(encoding="utf-8")),
    )

    base_headers = {
        "Content-Type": "application/json",
        "User-Agent": "orchestrator-e2e/1.0",
    }
    if cf_access_client_id and cf_access_client_secret:
        base_headers["CF-Access-Client-Id"] = cf_access_client_id
        base_headers["CF-Access-Client-Secret"] = cf_access_client_secret

    def post(path: str, payload: dict[str, object]) -> dict[str, object]:
        return _http_json(
            "POST",
            f"{tracking_uri}{path}",
            payload=payload,
            headers=base_headers,
            timeout=15,
        )

    def get(path: str, query: dict[str, str]) -> dict[str, object]:
        qs = parse.urlencode(query)
        return _http_json(
            "GET", f"{tracking_uri}{path}?{qs}", headers=base_headers, timeout=15
        )

    experiment_id = "0"
    try:
        run = post(
            "/api/2.0/mlflow/runs/create",
            {"experiment_id": experiment_id, "start_time": 0, "tags": []},
        )
    except error.HTTPError as exc:
        raise SystemExit(f"mlflow runs/create failed: HTTP {exc.code}") from exc

    run_obj = cast(dict[str, Any], run.get("run", {}))
    info_obj = cast(dict[str, Any], run_obj.get("info", {}))
    run_id = str(info_obj.get("run_id", ""))
    if not run_id:
        raise SystemExit("mlflow runs/create missing run_id")
    tags = {
        "artifact_manifest_uri": flow_uris["manifest"],
        "artifact_stdout_uri": flow_uris["stdout"],
        "artifact_stderr_uri": flow_uris["stderr"],
        "artifact_result_uri": flow_uris["result"],
        "e2e_flow_run_id": flow_run_id,
    }
    for key, value in tags.items():
        post(
            "/api/2.0/mlflow/runs/set-tag",
            {"run_id": run_id, "key": key, "value": value},
        )

    fetched = get("/api/2.0/mlflow/runs/get", {"run_id": run_id})
    fetched_run = cast(dict[str, Any], fetched.get("run", {}))
    fetched_data = cast(dict[str, Any], fetched_run.get("data", {}))
    rows = fetched_data.get("tags", [])
    if not isinstance(rows, list):
        raise SystemExit("mlflow runs/get tags is not a list")
    values = {
        str(row["key"]): str(row["value"])
        for row in rows
        if isinstance(row, dict) and "key" in row and "value" in row
    }
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
    summary_file.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8"
    )
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
    parser = argparse.ArgumentParser(
        description="Shell helper commands used by e2e scripts."
    )
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
    p.add_argument("--storage-api-url", required=True)
    p.add_argument("--cf-access-client-id", default="")
    p.add_argument("--cf-access-client-secret", default="")
    p.add_argument("--artifact-bucket", required=True)
    p.add_argument("--log-dir", required=True)
    p.add_argument("--presigned-host-header", default="")
    p.add_argument("--presigned-internal-base-url", default="")
    p.add_argument("--skip-engine-artifacts", action="store_true")
    p.set_defaults(func=cmd_verify_storage_objects)

    p = sub.add_parser("create-and-verify-mlflow-tags")
    p.add_argument("--mlflow-tracking-uri", required=True)
    p.add_argument("--flow-run-id", required=True)
    p.add_argument("--log-dir", required=True)
    p.add_argument("--cf-access-client-id", default="")
    p.add_argument("--cf-access-client-secret", default="")
    p.set_defaults(func=cmd_create_and_verify_mlflow_tags)

    p = sub.add_parser("verify-engine-mlflow-run")
    p.add_argument("--mlflow-tracking-uri", required=True)
    p.add_argument("--log-dir", required=True)
    p.add_argument("--cf-access-client-id", default="")
    p.add_argument("--cf-access-client-secret", default="")
    p.set_defaults(func=cmd_verify_engine_mlflow_run)

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
    func = cast(Callable[[argparse.Namespace], int], args.func)
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
