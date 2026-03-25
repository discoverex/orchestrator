#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${ROOT_DIR}"
source "./scripts/e2e/lib/common.sh"
source "./scripts/e2e/lib/local_orchestrator_workflow.inc"

PY_HELPER="./scripts/e2e/shell_python_helpers.py"
LOCAL_COMPOSE_FILE="scripts/e2e/docker-compose.local.test.yml"
LOCAL_PROJECT_NAME="orchestrator-e2e-local"
ENGINE_DIR="${ENGINE_DIR:-${ROOT_DIR}/tests/fixtures/dummy_engine_repo}"
ENGINE_JOB_SCRIPT="${ENGINE_DIR}/infra/register/register_orchestrator_job.py"
ENGINE_REPO_URL_CONTAINER="${ENGINE_REPO_URL_CONTAINER:-/opt/engine-src}"
ENGINE_BACKGROUND_ASSET_REF="${ENGINE_BACKGROUND_ASSET_REF:-bg://dummy}"

MODE="mlflow"; KEEP_ON_FAIL="false"; TIMEOUT_SEC="600"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="${2:-}"; shift 2 ;;
    --keep-on-fail) KEEP_ON_FAIL="true"; shift ;;
    --timeout-sec) TIMEOUT_SEC="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ "$MODE" != "core" && "$MODE" != "mlflow" ]] && { echo "--mode must be core or mlflow" >&2; exit 2; }
STAMP="$(date +%Y%m%d-%H%M%S)"; SUITE_NAME="e2e_${MODE}_local"
ARTIFACT_DIR="artifacts/e2e/${SUITE_NAME}/${STAMP}"
LOG_DIR="${ARTIFACT_DIR}/logs"; SUMMARY_FILE="${ARTIFACT_DIR}/summary.json"
STEPS_FILE="${ARTIFACT_DIR}/steps.tsv"; RUN_LOG="${LOG_DIR}/run.log"
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
REGISTER_FIXED_DEPLOYMENT_NAME="${REGISTER_FIXED_DEPLOYMENT_NAME:-e2e-test}"
TARGET_DEPLOYMENT_NAME="${TARGET_DEPLOYMENT_NAME:-e2e-job/${REGISTER_FIXED_DEPLOYMENT_NAME}}"
export PREFECT_API_URL PREFECT_WORK_POOL STORAGE_API_URL ARTIFACT_BUCKET ENGINE_LOCAL_REPO_PATH_HOST

FLOW_RUN_ID=""; MLFLOW_RUN_ID=""
log() { log_step_line "${RUN_LOG}" "$@"; }
record_step() { record_step_line "${STEPS_FILE}" "$1" "$2" "$3"; }
run_step() { run_step_cmd "${RUN_LOG}" "${STEPS_FILE}" "$@"; }
must_step() { must_step_cmd "${RUN_LOG}" "${STEPS_FILE}" collect_logs "$@"; }
trap cleanup EXIT

must_step "build.base_runtime" compose_local build base-runtime
compose_local down -v --remove-orphans >/dev/null 2>&1 || true
if [[ "${MODE}" == "mlflow" ]]; then
  must_step "compose.up_local_services" compose_local up -d --build minio prefect worker-router worker mlflow
else
  must_step "compose.up_local_services" compose_local up -d --build minio prefect worker-router worker
fi
must_step "health.wait_minio" wait_health orchestrator-e2e-local-minio 90
must_step "health.wait_prefect" wait_health orchestrator-e2e-local-prefect 90
must_step "health.wait_gateway" wait_health orchestrator-e2e-local-worker-router 90
[[ "${MODE}" == "mlflow" ]] && must_step "health.wait_mlflow" wait_health orchestrator-e2e-local-mlflow 90
must_step "prefect.ensure_work_pool" bash -lc "docker compose -p '${LOCAL_PROJECT_NAME}' -f '${LOCAL_COMPOSE_FILE}' exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect work-pool create ${PREFECT_WORK_POOL} --type process >/dev/null 2>&1 || true"

run_step "build.register_image" compose_local build register
run_step "register.apply_deployment" compose_local run --rm register
must_step "register.verify_deployment" bash -lc "docker compose -p '${LOCAL_PROJECT_NAME}' -f '${LOCAL_COMPOSE_FILE}' exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment inspect '${TARGET_DEPLOYMENT_NAME}' >/dev/null"

if [[ "${MODE}" == "mlflow" ]]; then
  cp scripts/e2e/fixed_dummy_inline_job.json "${LOG_DIR}/job-spec.json"
  # Override MLFLOW_TRACKING_URI to the internal one for the worker-router
  PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" uv run python - "${LOG_DIR}/job-spec.json" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
env = payload.get("env", {})
env["MLFLOW_TRACKING_URI"] = "http://worker-router:8200/mlflow"
payload["env"] = env
path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
PY
else
  must_step "engine.build_job_spec" build_engine_job_spec
fi

must_step "prefect.submit_flow_run" submit_prefect_run "${LOG_DIR}/job-spec.json"


FLOW_RUN_ID="$(grep -Eo '[0-9a-fA-F-]{36}' "${LOG_DIR}/prefect-submit.log" | head -n1 || true)"
if [[ -z "${FLOW_RUN_ID}" ]]; then
  record_step "prefect.extract_flow_run_id" "fail" "unable to parse flow run id"
  echo "FAILED: prefect.extract_flow_run_id" >&2
  echo "--- BEGIN PREFECT SUBMIT LOG ---" >&2
  cat "${LOG_DIR}/prefect-submit.log" >&2
  echo "--- END PREFECT SUBMIT LOG ---" >&2
  collect_logs; exit 1
fi
record_step "prefect.extract_flow_run_id" "pass" "${FLOW_RUN_ID}"

must_step "prefect.wait_flow_completion" poll_prefect_completion
must_step "storage.verify_objects" verify_storage_objects

if [[ "${MODE}" == "mlflow" ]]; then
  must_step "mlflow.verify_engine_run" verify_engine_mlflow_run_to_file "${LOG_DIR}/mlflow-run-id.txt"
  MLFLOW_RUN_ID="$(cat "${LOG_DIR}/mlflow-run-id.txt")"
fi

must_step "prefect.verify_flush" verify_prefect_flush
must_step "prefect.verify_prune" verify_prefect_prune

log "Local e2e succeeded: flow_run_id=${FLOW_RUN_ID}"
