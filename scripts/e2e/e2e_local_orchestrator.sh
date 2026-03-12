#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${ROOT_DIR}"
source "./scripts/e2e/lib/common.sh"

PY_HELPER="./scripts/e2e/shell_python_helpers.py"
LOCAL_COMPOSE_FILE="scripts/e2e/docker-compose.local.test.yml"
LOCAL_PROJECT_NAME="orchestrator-e2e-local"
ENGINE_DIR="${ENGINE_DIR:-${ROOT_DIR}/tests/fixtures/dummy_engine_repo}"
ENGINE_JOB_SCRIPT="${ENGINE_DIR}/infra/register/register_orchestrator_job.py"
ENGINE_REPO_URL_CONTAINER="${ENGINE_REPO_URL_CONTAINER:-/opt/engine-src}"
ENGINE_BACKGROUND_ASSET_REF="${ENGINE_BACKGROUND_ASSET_REF:-bg://dummy}"

compose_local() {
  docker compose -p "${LOCAL_PROJECT_NAME}" -f "${LOCAL_COMPOSE_FILE}" "$@"
}

MODE="mlflow"
KEEP_ON_FAIL="false"
TIMEOUT_SEC="600"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --keep-on-fail)
      KEEP_ON_FAIL="true"
      shift
      ;;
    --timeout-sec)
      TIMEOUT_SEC="${2:-}"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "$MODE" != "core" && "$MODE" != "mlflow" ]]; then
  echo "--mode must be one of: core, mlflow" >&2
  exit 2
fi

if ! [[ "$TIMEOUT_SEC" =~ ^[0-9]+$ ]]; then
  echo "--timeout-sec must be an integer" >&2
  exit 2
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
SUITE_NAME="e2e_${MODE}_local"
ARTIFACT_DIR="artifacts/e2e/${SUITE_NAME}/${STAMP}"
LOG_DIR="${ARTIFACT_DIR}/logs"
SUMMARY_FILE="${ARTIFACT_DIR}/summary.json"
STEPS_FILE="${ARTIFACT_DIR}/steps.tsv"
RUN_LOG="${LOG_DIR}/run.log"
mkdir -p "${LOG_DIR}"

PREFECT_API_URL="${PREFECT_API_URL:-http://127.0.0.1:24200/api}"
PREFECT_WORK_POOL="${PREFECT_WORK_POOL:-gpu-pool}"
STORAGE_API_URL="${STORAGE_API_URL:-http://127.0.0.1:8200}"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-orchestrator-artifacts}"
ENGINE_REPO_REF="${ENGINE_REPO_REF:-$(git -C "${ENGINE_DIR}" rev-parse HEAD)}"
ENGINE_LOCAL_REPO_PATH_HOST="${ENGINE_LOCAL_REPO_PATH_HOST:-${ENGINE_DIR}}"
ENGINE_MLFLOW_VERIFY_URI="${MLFLOW_TRACKING_URI:-http://127.0.0.1:25000}"
ENGINE_MLFLOW_TRACKING_URI="${ENGINE_MLFLOW_TRACKING_URI:-http://mlflow:5000}"
ENGINE_MLFLOW_S3_ENDPOINT_URL="${ENGINE_MLFLOW_S3_ENDPOINT_URL:-http://minio:9000}"
ENGINE_AWS_ACCESS_KEY_ID="${ENGINE_AWS_ACCESS_KEY_ID:-minioadmin}"
ENGINE_AWS_SECRET_ACCESS_KEY="${ENGINE_AWS_SECRET_ACCESS_KEY:-minioadmin}"
export PREFECT_API_URL PREFECT_WORK_POOL STORAGE_API_URL ARTIFACT_BUCKET
export ENGINE_LOCAL_REPO_PATH_HOST

FLOW_RUN_ID=""
MLFLOW_RUN_ID=""

log() { log_step_line "${RUN_LOG}" "$@"; }
record_step() { record_step_line "${STEPS_FILE}" "$1" "$2" "$3"; }
run_step() { run_step_cmd "${RUN_LOG}" "${STEPS_FILE}" "$@"; }

collect_logs() {
  log "collecting diagnostic logs"
  compose_local ps >"${LOG_DIR}/docker-local-ps.log" 2>&1 || true
  compose_local logs --no-color >"${LOG_DIR}/docker-local.log" 2>&1 || true
  compose_local exec -T worker sh -lc 'env | sort' >"${LOG_DIR}/worker-env.log" 2>&1 || true
  compose_local exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment ls >"${LOG_DIR}/prefect-deployments.log" 2>&1 || true
}

write_summary() {
  python3 "${PY_HELPER}" write-summary-local \
    --steps-file "${STEPS_FILE}" \
    --summary-file "${SUMMARY_FILE}" \
    --mode "${MODE}" \
    --flow-run-id "${FLOW_RUN_ID}" \
    --mlflow-run-id "${MLFLOW_RUN_ID}"
}

cleanup() {
  if [[ "${KEEP_ON_FAIL}" != "true" ]]; then
    compose_local down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  write_summary
}
trap cleanup EXIT

wait_health() {
  local name="$1"
  local timeout="$2"
  for _ in $(seq 1 "${timeout}"); do
    if [[ "$(docker inspect --format='{{.State.Health.Status}}' "${name}" 2>/dev/null || echo "starting")" == "healthy" ]]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

poll_prefect_completion() {
  compose_local exec -T \
    -e PREFECT_API_URL=http://127.0.0.1:4200/api \
    -e FLOW_RUN_ID="${FLOW_RUN_ID}" \
    -e TIMEOUT_SEC="${TIMEOUT_SEC}" \
    prefect python - <<'PY'
import json
import os
import time
from urllib import request

api_url = os.environ["PREFECT_API_URL"].rstrip("/")
flow_run_id = os.environ["FLOW_RUN_ID"]
timeout_sec = int(os.environ["TIMEOUT_SEC"])
deadline = time.time() + timeout_sec
terminal_success = {"COMPLETED"}
terminal_fail = {"FAILED", "CRASHED", "CANCELLED"}

while time.time() < deadline:
    with request.urlopen(f"{api_url}/flow_runs/{flow_run_id}", timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    state_type = str(payload.get("state_type") or "").upper()
    if state_type in terminal_success:
        print("COMPLETED")
        raise SystemExit(0)
    if state_type in terminal_fail:
        print(state_type)
        raise SystemExit(2)
    time.sleep(2)

print("TIMEOUT")
raise SystemExit(3)
PY
}

verify_storage_objects() {
  local extra_args=()
  if [[ "${MODE}" == "core" ]]; then
    extra_args+=(--skip-engine-artifacts)
  fi
  docker run --rm \
    --network "${LOCAL_PROJECT_NAME}_default" \
    -v "${ROOT_DIR}:/workspace" \
    -w /workspace \
    orchestrator-base:local \
    /bin/sh -lc "\
      /opt/venv/bin/python scripts/e2e/shell_python_helpers.py verify-storage-objects \
      --flow-run-id '${FLOW_RUN_ID}' \
      --storage-api-url 'http://worker-router:8200' \
      --cf-access-client-id '${CF_ACCESS_CLIENT_ID:-}' \
      --cf-access-client-secret '${CF_ACCESS_CLIENT_SECRET:-}' \
      --artifact-bucket '${ARTIFACT_BUCKET}' \
      --presigned-host-header '${STORAGE_DOWNLOAD_HOST_HEADER:-}' \
      --presigned-internal-base-url 'http://minio:9000' \
      --log-dir '/workspace/${LOG_DIR}' \
      ${extra_args[*]}"
}

verify_engine_mlflow_run() {
  local scene_id
  local version_id
  scene_id="$(
    python3 - "${LOG_DIR}/engine_output.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(str(payload.get("scene_id", "")).strip())
PY
  )"
  version_id="$(
    python3 - "${LOG_DIR}/engine_output.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(str(payload.get("version_id", "")).strip())
PY
  )"
  if [[ -z "${scene_id}" || -z "${version_id}" ]]; then
    echo "engine output missing scene_id/version_id" >&2
    return 1
  fi

  docker exec \
    -e E2E_SCENE_ID="${scene_id}" \
    -e E2E_VERSION_ID="${version_id}" \
    orchestrator-e2e-local-mlflow \
    python - <<'PY'
import os
import sqlite3
import sys

scene_id = os.environ["E2E_SCENE_ID"]
version_id = os.environ["E2E_VERSION_ID"]
conn = sqlite3.connect("/tmp/mlflow/mlflow.db")
cur = conn.cursor()
rows = cur.execute(
    """
    SELECT DISTINCT r.run_uuid
    FROM runs AS r
    JOIN params AS p_scene
      ON p_scene.run_uuid = r.run_uuid
     AND p_scene.key = 'scene_id'
    JOIN params AS p_version
      ON p_version.run_uuid = r.run_uuid
     AND p_version.key = 'version_id'
    WHERE r.experiment_id = 1
      AND p_scene.value = ?
      AND p_version.value = ?
    ORDER BY r.start_time DESC, r.run_uuid DESC
    LIMIT 1
    """,
    (scene_id, version_id),
).fetchall()
if not rows:
    raise SystemExit(
        f"no matching MLflow run found in sqlite for scene_id={scene_id} version_id={version_id}"
    )
print(rows[0][0])
PY
}

verify_prefect_flush() {
  local out_json="${LOG_DIR}/prefect-flush.json"
  docker run --rm \
    --network "${LOCAL_PROJECT_NAME}_default" \
    -v "${ROOT_DIR}:/workspace" \
    -w /workspace \
    orchestrator-base:local \
    /bin/sh -lc "\
      PREFECT_API_URL=http://prefect:4200/api \
      FLUSH_TARGET_URL=http://worker-router:8200/artifact \
      FLUSH_CURSOR_PATH=/workspace/${LOG_DIR}/prefect-flush-cursor.json \
      PYTHONPATH=src /opt/venv/bin/python scripts/ops/prefect_flush_completed.py --once --page-size 100 --max-runs 500 \
      > /workspace/${out_json}"

  python3 "${PY_HELPER}" verify-flush-output \
    --output-json "${out_json}" \
    --flow-run-id "${FLOW_RUN_ID}"
}

verify_prefect_prune() {
  local out_json="${LOG_DIR}/prefect-prune.json"
  docker run --rm \
    --network "${LOCAL_PROJECT_NAME}_default" \
    -v "${ROOT_DIR}:/workspace" \
    -w /workspace \
    orchestrator-base:local \
    /bin/sh -lc "\
      PREFECT_API_URL=http://prefect:4200/api \
      PYTHONPATH=src /opt/venv/bin/python scripts/ops/prefect_prune_completed.py --apply --ttl-hours 0 --page-size 200 --max-runs 1000 \
      > /workspace/${out_json}"

  compose_local exec -T \
    -e PREFECT_API_URL=http://127.0.0.1:4200/api \
    -e FLOW_RUN_ID="${FLOW_RUN_ID}" \
    prefect python - <<'PY'
import json
import os
from urllib import error, request

api_url = os.environ["PREFECT_API_URL"].rstrip("/")
flow_run_id = os.environ["FLOW_RUN_ID"]
try:
    with request.urlopen(f"{api_url}/flow_runs/{flow_run_id}", timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
except error.HTTPError as exc:
    if exc.code == 404:
        print("PRUNED")
        raise SystemExit(0)
    raise

state_type = str(payload.get("state_type") or "").upper()
if state_type == "CANCELLED":
    print("PRUNED")
    raise SystemExit(0)

raise SystemExit(f"flow run still present after prune: {state_type or 'UNKNOWN'}")
PY
}

build_engine_job_spec() {
  local job_spec_path="${LOG_DIR}/job-spec.json"
  if [[ "${MODE}" == "core" ]]; then
    python3 - <<'PY' >"${job_spec_path}"
import json
payload = {
    "run_mode": "inline",
    "engine": "shell",
    "entrypoint": [
        "/bin/sh",
        "-lc",
        "mkdir -p \"$ORCH_ENGINE_ARTIFACT_DIR/scene\" && printf '%s\n' '{\"scene_id\":\"local-e2e-scene\",\"version_id\":\"attempt-1\"}' > \"$ORCH_ENGINE_ARTIFACT_DIR/scene/scene.json\" && printf '%s\n' '{\"status\":\"ok\"}' > \"$ORCH_ENGINE_ARTIFACT_DIR/scene/verification.json\" && printf '%s\n' '{\"schema_version\":1,\"artifacts\":[{\"logical_name\":\"scene_json\",\"relative_path\":\"scene/scene.json\",\"content_type\":\"application/json\",\"mlflow_tag\":\"artifact_scene_uri\"},{\"logical_name\":\"verification_json\",\"relative_path\":\"scene/verification.json\",\"content_type\":\"application/json\",\"mlflow_tag\":\"artifact_verification_uri\"}]}' > \"$ORCH_ENGINE_ARTIFACT_MANIFEST_PATH\" && printf '%s\n' '{\"status\":\"ok\",\"scene_id\":\"local-e2e-scene\",\"version_id\":\"attempt-1\"}'",
    ],
    "config": None,
    "job_name": "local-e2e-dummy",
    "inputs": {},
    "env": {},
    "outputs_prefix": None,
}
print(json.dumps(payload, ensure_ascii=True))
PY
    echo "${job_spec_path}"
    return
  fi

  local profile="local-tiny-cpu"
  local extra_args=()
  if [[ "${MODE}" != "core" ]]; then
    extra_args+=(
      --mlflow-tracking-uri "${ENGINE_MLFLOW_TRACKING_URI}"
      --mlflow-s3-endpoint-url "${ENGINE_MLFLOW_S3_ENDPOINT_URL}"
      --aws-access-key-id "${ENGINE_AWS_ACCESS_KEY_ID}"
      --aws-secret-access-key "${ENGINE_AWS_SECRET_ACCESS_KEY}"
      --artifact-bucket "${ARTIFACT_BUCKET}"
    )
  fi
  uv run python "${ENGINE_JOB_SCRIPT}" \
    --dry-run \
    --run-mode inline \
    --entrypoint-shell-command "tmpdir=\$(mktemp -d /tmp/discoverex-engine-XXXXXX) && tar -C ${ENGINE_REPO_URL_CONTAINER} --exclude=.git --exclude=.venv --exclude=.cache --exclude=.ruff_cache -cf - . | tar -C \"\$tmpdir\" -xf - && cd \"\$tmpdir\" && PYTHONPATH=src python -m discoverex.orchestrator_contract.launcher" \
    --execution-profile "${profile}" \
    --command generate \
    --background-asset-ref "${ENGINE_BACKGROUND_ASSET_REF}" \
    "${extra_args[@]}" >"${job_spec_path}"
  python3 - "${job_spec_path}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
engine_run = payload.pop("engine_run", None)
if not isinstance(engine_run, dict):
    raise SystemExit("generated job spec missing engine_run payload")
payload["inputs"] = engine_run
env = payload.get("env")
if not isinstance(env, dict):
    env = {}
env["MLFLOW_TRACKING_PROXY_URL"] = "http://worker-router:8200/mlflow"
payload["env"] = env
path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
PY
  echo "${job_spec_path}"
}

submit_prefect_run() {
  local job_spec_path="$1"
  local job_spec_b64
  job_spec_b64="$(base64 -w0 <"${job_spec_path}")"
  docker compose -p "${LOCAL_PROJECT_NAME}" -f "${LOCAL_COMPOSE_FILE}" exec -T \
    -e PREFECT_API_URL=http://127.0.0.1:4200/api \
    -e JOB_SPEC_JSON_B64="${job_spec_b64}" \
    prefect sh -lc \
    'JOB_SPEC_JSON="$(printf %s "$JOB_SPEC_JSON_B64" | base64 -d)" && prefect deployment run "run-job/discoverex-engine-run" -p "job_spec_json=$JOB_SPEC_JSON"' \
    | tee "${LOG_DIR}/prefect-submit.log"
}

run_step "build.base_runtime" compose_local build base-runtime
compose_local down -v --remove-orphans >/dev/null 2>&1 || true
if [[ "${MODE}" == "mlflow" ]]; then
  run_step "compose.up_local_services" compose_local up -d --build minio prefect worker-router worker mlflow
else
  run_step "compose.up_local_services" compose_local up -d --build minio prefect worker-router worker
fi
run_step "health.wait_minio" wait_health orchestrator-e2e-local-minio 90
run_step "health.wait_prefect" wait_health orchestrator-e2e-local-prefect 90
run_step "health.wait_gateway" wait_health orchestrator-e2e-local-worker-router 90
if [[ "${MODE}" == "mlflow" ]]; then
  run_step "health.wait_mlflow" wait_health orchestrator-e2e-local-mlflow 90
fi
run_step "prefect.ensure_work_pool" bash -lc "docker compose -p '${LOCAL_PROJECT_NAME}' -f '${LOCAL_COMPOSE_FILE}' exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect work-pool create ${PREFECT_WORK_POOL} --type process >/dev/null 2>&1 || true"

run_step "build.register_image" compose_local build register
run_step "register.apply_deployment" compose_local run --rm register
run_step "register.verify_deployment" bash -lc "docker compose -p '${LOCAL_PROJECT_NAME}' -f '${LOCAL_COMPOSE_FILE}' exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment ls | grep -q 'run-job/discoverex-engine-run'"
run_step "engine.build_job_spec" build_engine_job_spec
run_step "prefect.submit_flow_run" submit_prefect_run "${LOG_DIR}/job-spec.json"
FLOW_RUN_ID="$(grep -Eo '[0-9a-fA-F-]{36}' "${LOG_DIR}/prefect-submit.log" | head -n1 || true)"
if [[ -z "${FLOW_RUN_ID}" ]]; then
  record_step "prefect.extract_flow_run_id" "fail" "unable to parse flow run id"
  collect_logs
  exit 1
fi
record_step "prefect.extract_flow_run_id" "pass" "${FLOW_RUN_ID}"

if poll_prefect_completion >>"${RUN_LOG}" 2>&1; then
  record_step "prefect.wait_flow_completion" "pass" "completed"
else
  record_step "prefect.wait_flow_completion" "fail" "did not complete"
  collect_logs
  exit 1
fi

if verify_storage_objects >>"${RUN_LOG}" 2>&1; then
  record_step "storage.verify_objects" "pass" "flow artifacts + engine scene bundle present"
else
  record_step "storage.verify_objects" "fail" "missing flow or engine artifacts"
  collect_logs
  exit 1
fi

if [[ "${MODE}" == "mlflow" ]]; then
  if MLFLOW_RUN_ID="$(verify_engine_mlflow_run 2>>"${RUN_LOG}")"; then
    record_step "mlflow.verify_engine_run" "pass" "${MLFLOW_RUN_ID}"
  else
    record_step "mlflow.verify_engine_run" "fail" "matching run not found"
    collect_logs
    exit 1
  fi
fi

if verify_prefect_flush >>"${RUN_LOG}" 2>&1; then
  record_step "prefect.verify_flush" "pass" "completed run snapshot uploaded"
else
  record_step "prefect.verify_flush" "fail" "flush missing or upload failed"
  collect_logs
  exit 1
fi

if verify_prefect_prune >>"${RUN_LOG}" 2>&1; then
  record_step "prefect.verify_prune" "pass" "completed run pruned by ttl"
else
  record_step "prefect.verify_prune" "fail" "prune apply failed or run not deleted"
  collect_logs
  exit 1
fi

log "Local e2e succeeded: flow_run_id=${FLOW_RUN_ID}"
