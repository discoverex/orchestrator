#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

REGISTER_ENV="${ROOT_DIR}/infra/stacks/register/.env"
REGISTER_COMPOSE="${ROOT_DIR}/infra/stacks/register/docker-compose.yml"
VERIFY_SCRIPT="${ROOT_DIR}/scripts/e2e/verify_remote_chain.py"
PY_HELPER="${ROOT_DIR}/scripts/e2e/shell_python_helpers.py"
ENGINE_DIR="${ENGINE_DIR:-${ROOT_DIR}/tests/fixtures/dummy_engine_repo}"
ENGINE_JOB_SCRIPT="${ENGINE_DIR}/infra/register/register_orchestrator_job.py"
LOCAL_TEST_COMPOSE="${ROOT_DIR}/scripts/e2e/docker-compose.local.test.yml"
source "${ROOT_DIR}/scripts/e2e/lib/common.sh"
source "${ROOT_DIR}/scripts/e2e/lib/remote_prefect_storage_workflow.inc"

load_env_file_if_exists "${ROOT_DIR}/.env"
load_env_file_if_exists "${ROOT_DIR}/infra/stacks/storage-node/.env"

PREFECT_API_URL="${PREFECT_API_URL:-}"
PREFECT_WORK_POOL="${PREFECT_WORK_POOL:-gpu-pool}"
PREFECT_WORK_QUEUE="${PREFECT_WORK_QUEUE:-gpu-fixed}"
CF_ACCESS_CLIENT_ID="${CF_ACCESS_CLIENT_ID:-}"
CF_ACCESS_CLIENT_SECRET="${CF_ACCESS_CLIENT_SECRET:-}"
STORAGE_API_URL="${STORAGE_API_URL:-https://storage-api.discoverex.qzz.io}"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-orchestrator-artifacts}"
MINIO_API_PORT="${MINIO_API_PORT:-9000}"
TIMEOUT_SEC="${TIMEOUT_SEC:-600}"
PRUNE_MODE="${PRUNE_MODE:-dry-run}"
PRUNE_TTL_HOURS="${PRUNE_TTL_HOURS:-72}"
RUN_MODE="${RUN_MODE:-engine}"
KEEP_ON_FAIL="false"; REGISTER_ONLY="false"; BOOTSTRAP_WORKER="false"
WORKER_CONTAINER_NAME="orchestrator-e2e-temp-worker"
FLOW_RUN_ID=""; JOB_SPEC_JSON=""; JOB_SPEC_FILE=""
ENGINE_REPO_URL="${ENGINE_REPO_URL:-$(git -C "${ENGINE_DIR}" remote get-url origin)}"
ENGINE_REPO_REF="${ENGINE_REPO_REF:-$(git -C "${ENGINE_DIR}" branch --show-current)}"
ENGINE_BACKGROUND_ASSET_REF="${ENGINE_BACKGROUND_ASSET_REF:-bg://dummy}"
ENGINE_EXECUTION_PROFILE="${ENGINE_EXECUTION_PROFILE:-remote-gpu-hf}"
ENGINE_MLFLOW_TRACKING_URI="${ENGINE_MLFLOW_TRACKING_URI:-${MLFLOW_TRACKING_URI:-}}"
ENGINE_MLFLOW_S3_ENDPOINT_URL="${ENGINE_MLFLOW_S3_ENDPOINT_URL:-${MLFLOW_S3_ENDPOINT_URL:-http://127.0.0.1:${MINIO_API_PORT}}}"
ENGINE_AWS_ACCESS_KEY_ID="${ENGINE_AWS_ACCESS_KEY_ID:-${MINIO_ACCESS_KEY:-}}"
ENGINE_AWS_SECRET_ACCESS_KEY="${ENGINE_AWS_SECRET_ACCESS_KEY:-${MINIO_SECRET_KEY:-}}"
MLFLOW_RUN_ID=""

ENGINE_REPO_URL="$(normalize_public_git_url "${ENGINE_REPO_URL}")"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefect-api-url) PREFECT_API_URL="${2:-}"; shift 2 ;;
    --work-pool) PREFECT_WORK_POOL="${2:-}"; shift 2 ;;
    --work-queue) PREFECT_WORK_QUEUE="${2:-}"; shift 2 ;;
    --storage-api-url) STORAGE_API_URL="${2:-}"; shift 2 ;;
    --prefect-access-client-id) CF_ACCESS_CLIENT_ID="${2:-}"; shift 2 ;;
    --prefect-access-client-secret) CF_ACCESS_CLIENT_SECRET="${2:-}"; shift 2 ;;
    --artifact-bucket) ARTIFACT_BUCKET="${2:-}"; shift 2 ;;
    --timeout-sec) TIMEOUT_SEC="${2:-}"; shift 2 ;;
    --mode) RUN_MODE="${2:-}"; shift 2 ;;
    --job-spec-json) JOB_SPEC_JSON="${2:-}"; shift 2 ;;
    --job-spec-file) JOB_SPEC_FILE="${2:-}"; shift 2 ;;
    --prune-mode) PRUNE_MODE="${2:-}"; shift 2 ;;
    --prune-ttl-hours) PRUNE_TTL_HOURS="${2:-}"; shift 2 ;;
    --register-only) REGISTER_ONLY="true"; shift ;;
    --bootstrap-worker) BOOTSTRAP_WORKER="true"; shift ;;
    --worker-container-name) WORKER_CONTAINER_NAME="${2:-}"; shift 2 ;;
    --keep-on-fail) KEEP_ON_FAIL="true"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -z "${PREFECT_API_URL}" ]] && { echo "missing Prefect API URL" >&2; exit 2; }
STAMP="$(date +%Y%m%d-%H%M%S)"; SUITE_NAME="e2e_remote_prefect_storage"
ARTIFACT_DIR="artifacts/e2e/${SUITE_NAME}/${STAMP}"; LOG_DIR="${ARTIFACT_DIR}/logs"
RUN_LOG="${LOG_DIR}/run.log"; STEPS_FILE="${ARTIFACT_DIR}/steps.tsv"; SUMMARY_FILE="${ARTIFACT_DIR}/summary.json"
mkdir -p "${LOG_DIR}"; touch "${STEPS_FILE}"

log() { log_step_line "${RUN_LOG}" "$@"; }
record_step() { record_step_line "${STEPS_FILE}" "$1" "$2" "$3"; }
run_step() { run_step_cmd "${RUN_LOG}" "${STEPS_FILE}" "$@"; }
must_step() { must_step_cmd "${RUN_LOG}" "${STEPS_FILE}" collect_diagnostics "$@"; }
trap cleanup EXIT

PREFECT_CUSTOM_HEADERS_JSON=""
if [[ -n "${CF_ACCESS_CLIENT_ID}" && -n "${CF_ACCESS_CLIENT_SECRET}" ]]; then
  PREFECT_CUSTOM_HEADERS_JSON="$(PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" uv run python "${PY_HELPER}" build-cf-headers-json --client-id "${CF_ACCESS_CLIENT_ID}" --client-secret "${CF_ACCESS_CLIENT_SECRET}")"
  export CF_ACCESS_CLIENT_ID CF_ACCESS_CLIENT_SECRET
fi

must_step "preflight.tools" bash -lc "command -v docker >/dev/null && command -v curl >/dev/null && command -v uv >/dev/null"
must_step "preflight.storage_api_health" curl -fsS "${STORAGE_API_URL%/}/healthz"
must_step "preflight.minio_health" curl -fsS "http://127.0.0.1:${MINIO_API_PORT}/minio/health/live"
must_step "engine.build_job_spec" build_engine_job_spec
must_step "build.base_register_worker_images" docker compose -f "${LOCAL_TEST_COMPOSE}" build base-runtime register worker
must_step "prefect.ensure_work_pool" bash -lc "docker run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' -e WORK_POOL='${PREFECT_WORK_POOL}' prefecthq/prefect:3-latest sh -lc 'prefect work-pool inspect \"\$WORK_POOL\" >/dev/null 2>&1 || prefect work-pool create \"\$WORK_POOL\" --type process'"
must_step "register.apply_deployment" bash -lc "run_register_compose() { if [[ -f '${REGISTER_ENV}' ]]; then docker compose --env-file '${REGISTER_ENV}' -f '${REGISTER_COMPOSE}' \"\$@\"; else docker compose -f '${REGISTER_COMPOSE}' \"\$@\"; fi; }; run_register_compose run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' -e PREFECT_WORK_POOL='${PREFECT_WORK_POOL}' -e PREFECT_WORK_QUEUE='${PREFECT_WORK_QUEUE}' register"
must_step "register.verify_deployment" bash -lc "docker run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' prefecthq/prefect:3-latest prefect deployment ls | grep -q 'e2e-job/e2e-test'"

if [[ "${REGISTER_ONLY}" == "true" ]]; then
  record_step "register.only" "pass" "stopped after register verification"
  log "Register-only mode completed."; exit 0
fi

if [[ "${BOOTSTRAP_WORKER}" == "true" ]]; then
  bootstrap_temp_worker
else
  record_step "worker.bootstrap_temp" "pass" "skipped (production worker expected)"
fi

JOB_SPEC_JSON_B64="$(base64 -w0 <"${LOG_DIR}/job-spec.json")"
must_step "prefect.submit_flow_run" bash -lc "docker run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' -e JOB_SPEC_JSON_B64='${JOB_SPEC_JSON_B64}' prefecthq/prefect:3-latest sh -lc 'JOB_SPEC_JSON=\"\$(printf %s \"\$JOB_SPEC_JSON_B64\" | base64 -d)\" && prefect deployment run \"e2e-job/e2e-test\" -p \"job_spec_json=\$JOB_SPEC_JSON\"' > '${LOG_DIR}/prefect-submit.log'"
FLOW_RUN_ID="$(grep -Eo '[0-9a-fA-F-]{36}' "${LOG_DIR}/prefect-submit.log" | head -n1 || true)"
if [[ -z "${FLOW_RUN_ID}" ]]; then
  record_step "prefect.extract_flow_run_id" "fail" "unable to parse flow run id"
  echo "FAILED: prefect.extract_flow_run_id" >&2
  echo "--- BEGIN PREFECT SUBMIT LOG ---" >&2
  cat "${LOG_DIR}/prefect-submit.log" >&2
  echo "--- END PREFECT SUBMIT LOG ---" >&2
  collect_diagnostics; exit 1
fi
record_step "prefect.extract_flow_run_id" "pass" "${FLOW_RUN_ID}"

must_step "prefect.wait_flow_completion" env PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" uv run python "${VERIFY_SCRIPT}" prefect-wait-completed --prefect-api-url "${PREFECT_API_URL}" --flow-run-id "${FLOW_RUN_ID}" --timeout-sec "${TIMEOUT_SEC}" --prefect-cf-access-client-id "${CF_ACCESS_CLIENT_ID}" --prefect-cf-access-client-secret "${CF_ACCESS_CLIENT_SECRET}"
storage_verify_args=(env PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" uv run python "${PY_HELPER}" verify-storage-objects --flow-run-id "${FLOW_RUN_ID}" --attempt 1 --storage-api-url "${STORAGE_API_URL}" --cf-access-client-id "${CF_ACCESS_CLIENT_ID}" --cf-access-client-secret "${CF_ACCESS_CLIENT_SECRET}" --artifact-bucket "${ARTIFACT_BUCKET}" --log-dir "${LOG_DIR}")
[[ "${RUN_MODE}" == "dummy" ]] && storage_verify_args+=(--skip-engine-artifacts)
must_step "storage.verify_objects" "${storage_verify_args[@]}"

if [[ "${RUN_MODE}" == "engine" ]]; then
  must_step "mlflow.verify_engine_run" bash -lc "PYTHONPATH='${ROOT_DIR}/src:${ROOT_DIR}' uv run python '${PY_HELPER}' verify-engine-mlflow-run --mlflow-tracking-uri '${ENGINE_MLFLOW_TRACKING_URI}' --log-dir '${LOG_DIR}' --cf-access-client-id '${CF_ACCESS_CLIENT_ID:-}' --cf-access-client-secret '${CF_ACCESS_CLIENT_SECRET:-}' > '${LOG_DIR}/mlflow-run-id.txt'"
  MLFLOW_RUN_ID="$(cat "${LOG_DIR}/mlflow-run-id.txt")"
else
  record_step "mlflow.verify_engine_run" "pass" "skipped for dummy mode"
fi
must_step "prefect.verify_flush" bash -lc "PYTHONPATH='${ROOT_DIR}/src:${ROOT_DIR}' uv run python '${VERIFY_SCRIPT}' flush-verify --prefect-api-url '${PREFECT_API_URL}' --storage-api-url '${STORAGE_API_URL}' --flow-run-id '${FLOW_RUN_ID}' --cursor-path '${LOG_DIR}/prefect-flush-cursor.json' --prefect-cf-access-client-id '${CF_ACCESS_CLIENT_ID}' --prefect-cf-access-client-secret '${CF_ACCESS_CLIENT_SECRET}'"

if [[ "${PRUNE_MODE}" == "apply" ]]; then
  must_step "prefect.verify_prune" bash -lc "PYTHONPATH='${ROOT_DIR}/src:${ROOT_DIR}' uv run python '${VERIFY_SCRIPT}' prune-verify --prefect-api-url '${PREFECT_API_URL}' --flow-run-id '${FLOW_RUN_ID}' --apply --ttl-hours '${PRUNE_TTL_HOURS}' --prefect-cf-access-client-id '${CF_ACCESS_CLIENT_ID}' --prefect-cf-access-client-secret '${CF_ACCESS_CLIENT_SECRET}'"
else
  must_step "prefect.verify_prune" bash -lc "PYTHONPATH='${ROOT_DIR}/src:${ROOT_DIR}' uv run python '${VERIFY_SCRIPT}' prune-verify --prefect-api-url '${PREFECT_API_URL}' --flow-run-id '${FLOW_RUN_ID}' --ttl-hours '${PRUNE_TTL_HOURS}' --prefect-cf-access-client-id '${CF_ACCESS_CLIENT_ID}' --prefect-cf-access-client-secret '${CF_ACCESS_CLIENT_SECRET}'"
fi

log "Remote e2e succeeded: flow_run_id=${FLOW_RUN_ID}"
