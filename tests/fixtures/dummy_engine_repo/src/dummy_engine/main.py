from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import parse, request


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _job_inputs() -> dict[str, object]:
    raw = os.getenv("ORCH_JOB_INPUTS_JSON", "").strip()
    if not raw:
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("ORCH_JOB_INPUTS_JSON must be a JSON object")
    return payload


def _mlflow_post(
    tracking_uri: str, path: str, payload: dict[str, object]
) -> dict[str, object]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "dummy-engine/1.0",
    }
    req = request.Request(
        f"{tracking_uri.rstrip('/')}{path}",
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:  # nosec B310
        raw = resp.read().decode("utf-8")
    parsed = json.loads(raw or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError("unexpected MLflow response")
    return parsed


def _mlflow_get(
    tracking_uri: str, path: str, query: dict[str, str]
) -> dict[str, object]:
    headers = {"User-Agent": "dummy-engine/1.0"}
    req = request.Request(
        f"{tracking_uri.rstrip('/')}{path}?{parse.urlencode(query)}",
        headers=headers,
        method="GET",
    )
    with request.urlopen(req, timeout=30) as resp:  # nosec B310
        raw = resp.read().decode("utf-8")
    parsed = json.loads(raw or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError("unexpected MLflow response")
    return parsed


def _maybe_create_mlflow_run(
    tracking_uri: str, flow_run_id: str, job_name: str, scene_id: str, version_id: str
) -> str:
    if not tracking_uri:
        return ""
    created = _mlflow_post(
        tracking_uri,
        "/api/2.0/mlflow/runs/create",
        {
            "experiment_id": "0",
            "start_time": 0,
            "tags": [
                {"key": "e2e_flow_run_id", "value": flow_run_id},
                {"key": "job_name", "value": job_name},
                {"key": "scene_id", "value": scene_id},
                {"key": "version_id", "value": version_id},
            ],
        },
    )
    run = created.get("run", {})
    info = run.get("info", {}) if isinstance(run, dict) else {}
    run_id = str(info.get("run_id", "")).strip()
    if not run_id:
        raise RuntimeError("mlflow run_id missing")
    _mlflow_post(
        tracking_uri,
        "/api/2.0/mlflow/runs/set-tag",
        {"run_id": run_id, "key": "dummy_engine_status", "value": "ok"},
    )
    fetched = _mlflow_get(
        tracking_uri, "/api/2.0/mlflow/runs/get", {"run_id": run_id}
    )
    fetched_run = fetched.get("run", {})
    fetched_info = fetched_run.get("info", {}) if isinstance(fetched_run, dict) else {}
    if str(fetched_info.get("run_id", "")).strip() != run_id:
        raise RuntimeError("mlflow run fetch mismatch")
    return run_id


def main() -> int:
    artifact_dir = Path(_required_env("ORCH_ENGINE_ARTIFACT_DIR"))
    manifest_path = Path(_required_env("ORCH_ENGINE_ARTIFACT_MANIFEST_PATH"))
    flow_run_id = _required_env("ORCH_FLOW_RUN_ID")
    inputs = _job_inputs()
    scene_id = str(inputs.get("scene_id", "dummy-scene")).strip() or "dummy-scene"
    version_id = str(inputs.get("version_id", "v1")).strip() or "v1"
    job_name = os.getenv("ORCH_JOB_NAME", "").strip() or "dummy-engine"
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()

    artifact_dir.mkdir(parents=True, exist_ok=True)
    scene_dir = artifact_dir / "scene"
    scene_dir.mkdir(parents=True, exist_ok=True)

    scene_path = scene_dir / "scene.json"
    verification_path = scene_dir / "verification.json"

    scene_path.write_text(
        json.dumps(
            {
                "scene_id": scene_id,
                "version_id": version_id,
                "flow_run_id": flow_run_id,
                "job_name": job_name,
                "inputs": inputs,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    verification_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "scene_id": scene_id,
                "version_id": version_id,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifacts": [
                    {
                        "logical_name": "scene_json",
                        "relative_path": "scene/scene.json",
                        "content_type": "application/json",
                        "mlflow_tag": "artifact_scene_uri",
                        "description": "Dummy generated scene payload",
                    },
                    {
                        "logical_name": "verification_json",
                        "relative_path": "scene/verification.json",
                        "content_type": "application/json",
                        "mlflow_tag": "artifact_verification_uri",
                        "description": "Dummy verification payload",
                    },
                ],
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    mlflow_run_id = _maybe_create_mlflow_run(
        tracking_uri, flow_run_id, job_name, scene_id, version_id
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "scene_id": scene_id,
                "version_id": version_id,
                "flow_run_id": flow_run_id,
                "mlflow_run_id": mlflow_run_id,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
