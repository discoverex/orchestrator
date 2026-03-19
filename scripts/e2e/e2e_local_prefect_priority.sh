#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${ROOT_DIR}"
source "./scripts/e2e/lib/common.sh"
source "./scripts/e2e/lib/local_orchestrator_workflow.inc"

PY_HELPER="./scripts/e2e/shell_python_helpers.py"
LOCAL_COMPOSE_FILE="scripts/e2e/docker-compose.local.test.yml"
LOCAL_PROJECT_NAME="orchestrator-e2e-local"

KEEP_ON_FAIL="false"; TIMEOUT_SEC="300"
PRIMARY_SLEEP_SEC="${PRIMARY_SLEEP_SEC:-12}"
BATCH_SLEEP_SEC="${BATCH_SLEEP_SEC:-4}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-on-fail) KEEP_ON_FAIL="true"; shift ;;
    --timeout-sec) TIMEOUT_SEC="${2:-}"; shift 2 ;;
    --primary-sleep-sec) PRIMARY_SLEEP_SEC="${2:-}"; shift 2 ;;
    --batch-sleep-sec) BATCH_SLEEP_SEC="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

STAMP="$(date +%Y%m%d-%H%M%S)"; SUITE_NAME="e2e_prefect_priority_local"
ARTIFACT_DIR="artifacts/e2e/${SUITE_NAME}/${STAMP}"
LOG_DIR="${ARTIFACT_DIR}/logs"; SUMMARY_FILE="${ARTIFACT_DIR}/summary.json"
STEPS_FILE="${ARTIFACT_DIR}/steps.tsv"; RUN_LOG="${LOG_DIR}/run.log"
mkdir -p "${LOG_DIR}"

MODE="priority"
PREFECT_API_URL="${PREFECT_API_URL:-http://127.0.0.1:24200/api}"
PREFECT_WORK_POOL="${PREFECT_WORK_POOL:-gpu-pool}"
PRIMARY_QUEUE="${PREFECT_WORK_QUEUE:-gpu-fixed}"
BATCH_QUEUE="${PREFECT_BATCH_WORK_QUEUE:-${PRIMARY_QUEUE}-batch}"
PRIMARY_DEPLOYMENT_NAME="${PRIMARY_DEPLOYMENT_NAME:-e2e-priority-primary}"
BATCH_DEPLOYMENT_NAME="${BATCH_DEPLOYMENT_NAME:-e2e-priority-batch}"
export PREFECT_API_URL PREFECT_WORK_POOL

FLOW_RUN_ID=""
PRIMARY_FLOW_RUN_ID=""
BATCH_FLOW_RUN_ID=""
MLFLOW_RUN_ID=""
log() { log_step_line "${RUN_LOG}" "$@"; }
record_step() { record_step_line "${STEPS_FILE}" "$1" "$2" "$3"; }
run_step() { run_step_cmd "${RUN_LOG}" "${STEPS_FILE}" "$@"; }
must_step() { must_step_cmd "${RUN_LOG}" "${STEPS_FILE}" collect_logs "$@"; }
trap cleanup EXIT

must_step "build.base_runtime" compose_local build base-runtime
compose_local down -v --remove-orphans >/dev/null 2>&1 || true
must_step "compose.up_local_services" compose_local up -d --build minio prefect worker-router
must_step "health.wait_minio" wait_health orchestrator-e2e-local-minio 90
must_step "health.wait_prefect" wait_health orchestrator-e2e-local-prefect 90
must_step "health.wait_gateway" wait_health orchestrator-e2e-local-worker-router 90

run_step "build.register_image" compose_local build register
must_step "prefect.ensure_work_queues" compose_local run --rm --entrypoint python register -m common.prefect.work_queues --pool "${PREFECT_WORK_POOL}" --primary-queue "${PRIMARY_QUEUE}" --batch-queue "${BATCH_QUEUE}"
must_step "register.primary_deployment" compose_local run --rm -e REGISTER_DEPLOYMENT_MODE=single -e REGISTER_DEPLOYMENT_NAME="${PRIMARY_DEPLOYMENT_NAME}" -e PREFECT_WORK_QUEUE="${PRIMARY_QUEUE}" register
must_step "register.batch_deployment" compose_local run --rm -e REGISTER_DEPLOYMENT_MODE=single -e REGISTER_DEPLOYMENT_NAME="${BATCH_DEPLOYMENT_NAME}" -e PREFECT_WORK_QUEUE="${BATCH_QUEUE}" register
must_step "register.verify_primary_deployment" bash -lc "docker compose -p '${LOCAL_PROJECT_NAME}' -f '${LOCAL_COMPOSE_FILE}' exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment inspect 'e2e-job/${PRIMARY_DEPLOYMENT_NAME}' >/dev/null"
must_step "register.verify_batch_deployment" bash -lc "docker compose -p '${LOCAL_PROJECT_NAME}' -f '${LOCAL_COMPOSE_FILE}' exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment inspect 'e2e-job/${BATCH_DEPLOYMENT_NAME}' >/dev/null"

must_step "job.build_primary_spec" build_sleep_job_spec "${LOG_DIR}/primary-job-spec.json" "priority-primary" "${PRIMARY_SLEEP_SEC}"
must_step "job.build_batch_spec" build_sleep_job_spec "${LOG_DIR}/batch-job-spec.json" "priority-batch" "${BATCH_SLEEP_SEC}"
must_step "prefect.submit_batch_flow_run" submit_prefect_run "${LOG_DIR}/batch-job-spec.json" "e2e-job/${BATCH_DEPLOYMENT_NAME}" "${LOG_DIR}/prefect-submit-batch.log"
must_step "prefect.submit_primary_flow_run" submit_prefect_run "${LOG_DIR}/primary-job-spec.json" "e2e-job/${PRIMARY_DEPLOYMENT_NAME}" "${LOG_DIR}/prefect-submit-primary.log"

# verify-prefect-priority / wait-prefect-state names are kept for contract parity.
BATCH_FLOW_RUN_ID="$(grep -Eo '[0-9a-fA-F-]{36}' "${LOG_DIR}/prefect-submit-batch.log" | head -n1 || true)"
PRIMARY_FLOW_RUN_ID="$(grep -Eo '[0-9a-fA-F-]{36}' "${LOG_DIR}/prefect-submit-primary.log" | head -n1 || true)"
if [[ -z "${BATCH_FLOW_RUN_ID}" || -z "${PRIMARY_FLOW_RUN_ID}" ]]; then
  record_step "prefect.extract_flow_run_ids" "fail" "unable to parse priority flow run ids"
  echo "FAILED: prefect.extract_flow_run_ids" >&2
  collect_logs
  exit 1
fi
record_step "prefect.extract_flow_run_ids" "pass" "primary=${PRIMARY_FLOW_RUN_ID} batch=${BATCH_FLOW_RUN_ID}"

must_step "compose.up_worker" compose_local up -d --build worker
must_step "prefect.verify_priority_order" verify_prefect_priority_local "${PRIMARY_FLOW_RUN_ID}" "${BATCH_FLOW_RUN_ID}" "${TIMEOUT_SEC}"
must_step "prefect.wait_primary_completion" wait_prefect_state_local "${PRIMARY_FLOW_RUN_ID}" "COMPLETED" "${TIMEOUT_SEC}"
must_step "prefect.wait_batch_completion" wait_prefect_state_local "${BATCH_FLOW_RUN_ID}" "COMPLETED" "${TIMEOUT_SEC}"

FLOW_RUN_ID="${PRIMARY_FLOW_RUN_ID}"
log "Prefect priority e2e succeeded: primary=${PRIMARY_FLOW_RUN_ID} batch=${BATCH_FLOW_RUN_ID}"
