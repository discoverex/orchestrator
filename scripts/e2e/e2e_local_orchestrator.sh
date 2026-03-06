#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
source "./scripts/e2e/lib/common.sh"
PY_HELPER="./scripts/e2e/shell_python_helpers.py"
LOCAL_COMPOSE_FILE="scripts/e2e/docker-compose.local.test.yml"
LOCAL_PROJECT_NAME="orchestrator-e2e-local"

compose_local() {
  docker compose -p "${LOCAL_PROJECT_NAME}" -f "${LOCAL_COMPOSE_FILE}" "$@"
}

MODE="core"
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
PREFECT_WORK_POOL="${PREFECT_WORK_POOL:-colab-gpu}"
STORAGE_GATEWAY_URL="${STORAGE_GATEWAY_URL:-http://127.0.0.1:28100}"
STORAGE_GATEWAY_TOKEN="${STORAGE_GATEWAY_TOKEN:-dev-storage-token}"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-orchestrator-artifacts}"
export PREFECT_API_URL PREFECT_WORK_POOL STORAGE_GATEWAY_URL STORAGE_GATEWAY_TOKEN ARTIFACT_BUCKET

FLOW_RUN_ID=""
MLFLOW_RUN_ID=""

log() { log_step_line "${RUN_LOG}" "$@"; }
record_step() { record_step_line "${STEPS_FILE}" "$1" "$2" "$3"; }
run_step() { run_step_cmd "${RUN_LOG}" "${STEPS_FILE}" "$@"; }

require_env() {
  local key="$1"
  if [[ -z "${!key:-}" ]]; then
    log "missing required env: ${key}"
    record_step "env.required_${key}" "fail" "missing required env"
    exit 1
  fi
}

collect_logs() {
  log "collecting diagnostic logs"
  compose_local ps >"${LOG_DIR}/docker-local-ps.log" 2>&1 || true
  compose_local logs --no-color >"${LOG_DIR}/docker-local.log" 2>&1 || true
  docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml ps >"${LOG_DIR}/docker-storage-ps.log" 2>&1 || true
  docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml logs --no-color >"${LOG_DIR}/docker-storage.log" 2>&1 || true
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
  compose_local down -v --remove-orphans >/dev/null 2>&1 || true
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
  python3 "${PY_HELPER}" poll-prefect-completion \
    --prefect-api-url "${PREFECT_API_URL}" \
    --flow-run-id "${FLOW_RUN_ID}" \
    --timeout-sec "${TIMEOUT_SEC}"
}

verify_storage_objects() {
  python3 "${PY_HELPER}" verify-storage-objects \
    --flow-run-id "${FLOW_RUN_ID}" \
    --storage-gateway-url "${STORAGE_GATEWAY_URL}" \
    --storage-gateway-token "${STORAGE_GATEWAY_TOKEN}" \
    --artifact-bucket "${ARTIFACT_BUCKET}" \
    --log-dir "${LOG_DIR}"
}

create_and_verify_mlflow_tags() {
  python3 "${PY_HELPER}" create-and-verify-mlflow-tags \
    --mlflow-tracking-uri "${MLFLOW_TRACKING_URI}" \
    --flow-run-id "${FLOW_RUN_ID}" \
    --log-dir "${LOG_DIR}" \
    --cf-access-client-id "${CF_ACCESS_CLIENT_ID:-}" \
    --cf-access-client-secret "${CF_ACCESS_CLIENT_SECRET:-}"
}

check_mlflow_tracking_access() {
  require_env MLFLOW_TRACKING_URI
  local code

  if [[ -n "${CF_ACCESS_CLIENT_ID:-}" && -n "${CF_ACCESS_CLIENT_SECRET:-}" ]]; then
    code="$(
      curl -sS -o /dev/null -w "%{http_code}" \
        -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
        -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
        -H "Content-Type: application/json" \
        -d '{"max_results": 1}' \
        "${MLFLOW_TRACKING_URI%/}/api/2.0/mlflow/experiments/search"
    )"
  else
    code="$(
      curl -sS -o /dev/null -w "%{http_code}" \
        -H "Content-Type: application/json" \
        -d '{"max_results": 1}' \
        "${MLFLOW_TRACKING_URI%/}/api/2.0/mlflow/experiments/search"
    )"
  fi

  [[ "${code}" == "200" ]]
}

uri_host() {
  local uri="$1"
  python3 "${PY_HELPER}" uri-host --uri "${uri}"
}

verify_mlflow_prereqs() {
  require_env MLFLOW_TRACKING_URI

  local tracking_host
  tracking_host="$(uri_host "${MLFLOW_TRACKING_URI}")"

  getent ahosts "${tracking_host}" >/dev/null
}

verify_prefect_flush() {
  local out_json="${LOG_DIR}/prefect-flush.json"
  PREFECT_API_URL="${PREFECT_API_URL}" \
  FLUSH_TARGET_URL="${STORAGE_GATEWAY_URL}" \
  FLUSH_GATEWAY_TOKEN="${STORAGE_GATEWAY_TOKEN}" \
  FLUSH_CURSOR_PATH="${LOG_DIR}/prefect-flush-cursor.json" \
  python3 scripts/ops/prefect_flush_completed.py --once --page-size 100 --max-runs 500 >"${out_json}"

  python3 "${PY_HELPER}" verify-flush-output \
    --output-json "${out_json}" \
    --flow-run-id "${FLOW_RUN_ID}"
}

verify_prefect_prune() {
  local out_json="${LOG_DIR}/prefect-prune.json"
  PREFECT_API_URL="${PREFECT_API_URL}" \
  python3 scripts/ops/prefect_prune_completed.py --apply --ttl-hours 0 --page-size 200 --max-runs 1000 >"${out_json}"

  python3 "${PY_HELPER}" verify-prune-removed \
    --prefect-api-url "${PREFECT_API_URL}" \
    --flow-run-id "${FLOW_RUN_ID}"
}

run_step "build.base_runtime" compose_local build base-runtime
if [[ "${MODE}" == "mlflow" ]]; then
  MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://127.0.0.1:25000}"
  export MLFLOW_TRACKING_URI
  run_step "compose.up_local_services" compose_local up -d --build minio prefect storage-gateway worker mlflow
else
  run_step "compose.up_local_services" compose_local up -d --build minio prefect storage-gateway worker
fi
run_step "health.wait_minio" wait_health orchestrator-e2e-local-minio 90
run_step "health.wait_prefect" wait_health orchestrator-e2e-local-prefect 90
run_step "health.wait_gateway" wait_health orchestrator-e2e-local-storage-gateway 90
if [[ "${MODE}" == "mlflow" ]]; then
  run_step "health.wait_mlflow" wait_health orchestrator-e2e-local-mlflow 90
fi
run_step "prefect.ensure_work_pool" bash -lc "docker compose -p '${LOCAL_PROJECT_NAME}' -f '${LOCAL_COMPOSE_FILE}' exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect work-pool create ${PREFECT_WORK_POOL} --type process >/dev/null 2>&1 || true"

run_step "build.register_image" compose_local build register
run_step "register.apply_deployment" compose_local run --rm register
run_step "register.verify_deployment" bash -lc "docker compose -p '${LOCAL_PROJECT_NAME}' -f '${LOCAL_COMPOSE_FILE}' exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment ls | grep -q 'run-job/engine-run'"

run_step "prefect.submit_flow_run" bash -lc "docker compose -p '${LOCAL_PROJECT_NAME}' -f '${LOCAL_COMPOSE_FILE}' exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment run 'run-job/engine-run' -p job_spec_json='{\"engine\":\"shell\",\"repo_url\":\"https://github.com/octocat/Hello-World.git\",\"ref\":\"master\",\"entrypoint\":[\"/bin/sh\",\"-lc\",\"echo hello-prefect\"],\"config\":null,\"inputs\":{},\"env\":{},\"outputs_prefix\":null}' > '${LOG_DIR}/prefect-submit.log'"
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
  record_step "storage.verify_objects" "pass" "stdout/stderr/result/manifest present"
else
  record_step "storage.verify_objects" "fail" "missing object or invalid manifest"
  collect_logs
  exit 1
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

if [[ "${MODE}" == "mlflow" ]]; then
  if verify_mlflow_prereqs >>"${RUN_LOG}" 2>&1; then
    record_step "mlflow.verify_prereqs" "pass" "tracking env present + DNS resolved"
  else
    record_step "mlflow.verify_prereqs" "fail" "missing env or DNS not resolved"
    collect_logs
    exit 1
  fi
  if check_mlflow_tracking_access >>"${RUN_LOG}" 2>&1; then
    record_step "mlflow.verify_tracking_access" "pass" "mlflow API reachable"
  else
    record_step "mlflow.verify_tracking_access" "fail" "mlflow API returned non-200"
    collect_logs
    exit 1
  fi
  if MLFLOW_RUN_ID="$(create_and_verify_mlflow_tags 2>>"${RUN_LOG}")"; then
    record_step "mlflow.verify_tags" "pass" "${MLFLOW_RUN_ID}"
  else
    record_step "mlflow.verify_tags" "fail" "mlflow create/get tag check failed"
    collect_logs
    exit 1
  fi
fi

log "E2E succeeded: mode=${MODE} flow_run_id=${FLOW_RUN_ID} mlflow_run_id=${MLFLOW_RUN_ID:-N/A}"
