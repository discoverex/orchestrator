from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from urllib import error

from scripts.e2e.lib.shell_helpers.http import encode_query, http_json


def find_mlflow_experiment_id(
    tracking_uri: str, experiment_name: str, headers: dict[str, str]
) -> str:
    for url in (
        f"{tracking_uri}/api/2.0/mlflow/experiments/get-by-name?experiment_name={experiment_name}",
        f"{tracking_uri}/api/2.0/mlflow/experiments/search",
    ):
        try:
            payload = http_json(
                "GET" if "get-by-name" in url else "POST",
                url,
                payload=None
                if "get-by-name" in url
                else {"filter": f"name = '{experiment_name}'", "max_results": 20},
                headers=headers,
                timeout=20,
            )
        except error.HTTPError as exc:
            if exc.code != 404:
                raise
            continue
        row = payload.get("experiment") if "experiment" in payload else None
        if isinstance(row, dict):
            experiment_id = str(row.get("experiment_id", "")).strip()
            if experiment_id:
                return experiment_id
        exps = cast(list[Any], payload.get("experiments", []))
        for candidate in exps:
            if (
                isinstance(candidate, dict)
                and str(candidate.get("name")) == experiment_name
            ):
                eid = str(candidate.get("experiment_id", "")).strip()
                if eid:
                    return eid
    for cid in range(21):
        try:
            payload = http_json(
                "GET",
                f"{tracking_uri}/api/2.0/mlflow/experiments/get?experiment_id={cid}",
                headers=headers,
                timeout=20,
            )
        except error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        exp = payload.get("experiment")
        if isinstance(exp, dict) and str(exp.get("name")) == experiment_name:
            eid = str(exp.get("experiment_id", "")).strip()
            if eid:
                return eid
    return ""


def verify_engine_mlflow_run(args: Any) -> int:
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
    experiment_id = find_mlflow_experiment_id(tracking_uri, "discoverex-core", headers)
    candidate_ids = [experiment_id] if experiment_id else []
    candidate_ids.extend(str(i) for i in range(21) if str(i) != experiment_id)
    for candidate_id in candidate_ids:
        try:
            runs = http_json(
                "POST",
                f"{tracking_uri}/api/2.0/mlflow/runs/search",
                payload={"experiment_ids": [candidate_id], "max_results": 20},
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
        for row in rows:
            if not isinstance(row, dict):
                continue
            if mlflow_run_matches_scene_version(row, scene_id, version_id):
                run_id = str(
                    cast(dict[str, object], row.get("info", {})).get("run_id", "")
                ).strip()
                if not run_id:
                    raise SystemExit("mlflow run_id missing")
                print(run_id)
                return 0
    raise SystemExit("no matching MLflow run found for engine scene output")


def mlflow_run_matches_scene_version(
    run: dict[str, object], scene_id: str, version_id: str
) -> bool:
    data = run.get("data", {})
    if not isinstance(data, dict):
        return False
    params = data.get("params", [])
    if not isinstance(params, list):
        return False
    values = {
        str(row.get("key", "")): str(row.get("value", ""))
        for row in params
        if isinstance(row, dict)
    }
    return values.get("scene_id") == scene_id and values.get("version_id") == version_id


def create_and_verify_mlflow_tags(args: Any) -> int:
    tracking_uri = args.mlflow_tracking_uri.rstrip("/")
    flow_uris = cast(
        dict[str, str],
        json.loads((Path(args.log_dir) / "flow_uris.json").read_text(encoding="utf-8")),
    )
    headers = {"Content-Type": "application/json", "User-Agent": "orchestrator-e2e/1.0"}
    if args.cf_access_client_id and args.cf_access_client_secret:
        headers["CF-Access-Client-Id"] = args.cf_access_client_id
        headers["CF-Access-Client-Secret"] = args.cf_access_client_secret
    run = http_json(
        "POST",
        f"{tracking_uri}/api/2.0/mlflow/runs/create",
        payload={"experiment_id": "0", "start_time": 0, "tags": []},
        headers=headers,
        timeout=15,
    )
    run_id = str(
        cast(
            dict[str, object],
            cast(dict[str, object], run.get("run", {})).get("info", {}),
        ).get("run_id", "")
    )
    if not run_id:
        raise SystemExit("mlflow runs/create missing run_id")
    tags = {
        "artifact_manifest_uri": flow_uris["manifest"],
        "artifact_stdout_uri": flow_uris["stdout"],
        "artifact_stderr_uri": flow_uris["stderr"],
        "artifact_result_uri": flow_uris["result"],
        "e2e_flow_run_id": args.flow_run_id,
    }
    for key, value in tags.items():
        http_json(
            "POST",
            f"{tracking_uri}/api/2.0/mlflow/runs/set-tag",
            payload={"run_id": run_id, "key": key, "value": value},
            headers=headers,
            timeout=15,
        )
    fetched = http_json(
        "GET",
        f"{tracking_uri}/api/2.0/mlflow/runs/get?{encode_query({'run_id': run_id})}",
        headers=headers,
        timeout=15,
    )
    rows = cast(
        dict[str, object],
        cast(dict[str, object], fetched.get("run", {})).get("data", {}),
    ).get("tags", [])
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
