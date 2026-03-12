from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast
from urllib import error

from ..http import http_json
from ..mlflow import find_mlflow_experiment_id, mlflow_run_matches_scene_version


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

    experiment_id = find_mlflow_experiment_id(
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
            runs = http_json(
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
            and mlflow_run_matches_scene_version(
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
        return http_json(
            "POST",
            f"{tracking_uri}{path}",
            payload=payload,
            headers=base_headers,
            timeout=15,
        )

    run = post(
        "/api/2.0/mlflow/runs/create",
        {"experiment_id": "0", "start_time": 0, "tags": []},
    )
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
    print(run_id)
    return 0
