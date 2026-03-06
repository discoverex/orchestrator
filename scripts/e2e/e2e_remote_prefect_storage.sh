#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

REGISTER_ENV="${ROOT_DIR}/infra/stacks/register/.env"
REGISTER_COMPOSE="${ROOT_DIR}/infra/stacks/register/docker-compose.yml"
VERIFY_SCRIPT="${ROOT_DIR}/scripts/e2e/verify_remote_chain.py"
PY_HELPER="${ROOT_DIR}/scripts/e2e/shell_python_helpers.py"
LOCAL_TEST_COMPOSE="${ROOT_DIR}/scripts/e2e/docker-compose.local.test.yml"
source "${ROOT_DIR}/scripts/e2e/lib/common.sh"

load_env_file_if_exists "${ROOT_DIR}/.env"
load_env_file_if_exists "${ROOT_DIR}/infra/stacks/storage-node/.env"

PREFECT_API_URL="${PREFECT_API_URL:-}"
PREFECT_WORK_POOL="${PREFECT_WORK_POOL:-gpu-pool}"
PREFECT_WORK_QUEUE="${PREFECT_WORK_QUEUE:-gpu-fixed}"
PREFECT_CF_ACCESS_CLIENT_ID="${PREFECT_CF_ACCESS_CLIENT_ID:-${CF_ACCESS_CLIENT_ID:-}}"
PREFECT_CF_ACCESS_CLIENT_SECRET="${PREFECT_CF_ACCESS_CLIENT_SECRET:-${CF_ACCESS_CLIENT_SECRET:-}}"
STORAGE_GATEWAY_URL="${STORAGE_GATEWAY_URL:-http://127.0.0.1:8100}"
STORAGE_GATEWAY_TOKEN="${STORAGE_GATEWAY_TOKEN:-}"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-orchestrator-artifacts}"
TIMEOUT_SEC="${TIMEOUT_SEC:-600}"
PRUNE_MODE="${PRUNE_MODE:-dry-run}"
PRUNE_TTL_HOURS="${PRUNE_TTL_HOURS:-72}"
KEEP_ON_FAIL="false"
REGISTER_ONLY="false"
BOOTSTRAP_WORKER="false"
WORKER_CONTAINER_NAME="orchestrator-e2e-temp-worker"
FLOW_RUN_ID=""

usage() {
  cat <<'EOF'
Usage:
  scripts/e2e/e2e_remote_prefect_storage.sh --prefect-api-url URL [options]

Options:
  --prefect-api-url URL         Remote Prefect API URL (e.g. https://<host>/api)
  --work-pool NAME              Prefect work pool name (default: gpu-pool)
  --work-queue NAME             Prefect work queue name (default: gpu-fixed)
  --prefect-cf-access-client-id ID
  --prefect-cf-access-client-secret SECRET
  --storage-gateway-url URL     Local storage-gateway URL (default: http://127.0.0.1:8100)
  --storage-gateway-token TOK   storage-gateway bearer token
  --artifact-bucket NAME        Artifact bucket name (default: orchestrator-artifacts)
  --timeout-sec N               Timeout for flow completion (default: 600)
  --prune-mode dry-run|apply    Prune validation mode (default: dry-run)
  --prune-ttl-hours N           TTL hours passed to prune (default: 72)
  --register-only               Stop after deployment register/verify
  --bootstrap-worker            Start temporary docker worker (for bootstrapping only)
  --worker-container-name NAME  Temporary worker container name
  --keep-on-fail                Keep temporary worker and logs on failure

Notes:
  - This script is designed for production-worker validation. The temporary worker
    section is intentionally isolated for easy removal during cutover.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefect-api-url)
      PREFECT_API_URL="${2:-}"
      shift 2
      ;;
    --work-pool)
      PREFECT_WORK_POOL="${2:-}"
      shift 2
      ;;
    --work-queue)
      PREFECT_WORK_QUEUE="${2:-}"
      shift 2
      ;;
    --storage-gateway-url)
      STORAGE_GATEWAY_URL="${2:-}"
      shift 2
      ;;
    --prefect-cf-access-client-id)
      PREFECT_CF_ACCESS_CLIENT_ID="${2:-}"
      shift 2
      ;;
    --prefect-cf-access-client-secret)
      PREFECT_CF_ACCESS_CLIENT_SECRET="${2:-}"
      shift 2
      ;;
    --storage-gateway-token)
      STORAGE_GATEWAY_TOKEN="${2:-}"
      shift 2
      ;;
    --artifact-bucket)
      ARTIFACT_BUCKET="${2:-}"
      shift 2
      ;;
    --timeout-sec)
      TIMEOUT_SEC="${2:-}"
      shift 2
      ;;
    --prune-mode)
      PRUNE_MODE="${2:-}"
      shift 2
      ;;
    --prune-ttl-hours)
      PRUNE_TTL_HOURS="${2:-}"
      shift 2
      ;;
    --register-only)
      REGISTER_ONLY="true"
      shift
      ;;
    --bootstrap-worker)
      BOOTSTRAP_WORKER="true"
      shift
      ;;
    --worker-container-name)
      WORKER_CONTAINER_NAME="${2:-}"
      shift 2
      ;;
    --keep-on-fail)
      KEEP_ON_FAIL="true"
      shift
      ;;
    help|-h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "${PREFECT_API_URL}" ]]; then
  echo "missing required --prefect-api-url" >&2
  exit 2
fi

if [[ -z "${STORAGE_GATEWAY_TOKEN}" ]]; then
  echo "missing storage gateway token; pass --storage-gateway-token or set STORAGE_GATEWAY_TOKEN" >&2
  exit 2
fi

if [[ "${PRUNE_MODE}" != "dry-run" && "${PRUNE_MODE}" != "apply" ]]; then
  echo "--prune-mode must be dry-run or apply" >&2
  exit 2
fi

if ! [[ "${TIMEOUT_SEC}" =~ ^[0-9]+$ ]]; then
  echo "--timeout-sec must be an integer" >&2
  exit 2
fi

if ! [[ "${PRUNE_TTL_HOURS}" =~ ^[0-9]+$ ]]; then
  echo "--prune-ttl-hours must be an integer" >&2
  exit 2
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
SUITE_NAME="e2e_remote_prefect_storage"
ARTIFACT_DIR="artifacts/e2e/${SUITE_NAME}/${STAMP}"
LOG_DIR="${ARTIFACT_DIR}/logs"
RUN_LOG="${LOG_DIR}/run.log"
STEPS_FILE="${ARTIFACT_DIR}/steps.tsv"
SUMMARY_FILE="${ARTIFACT_DIR}/summary.json"
mkdir -p "${LOG_DIR}"
touch "${STEPS_FILE}"

log() { log_step_line "${RUN_LOG}" "$@"; }
record_step() { record_step_line "${STEPS_FILE}" "$1" "$2" "$3"; }
run_step() { run_step_cmd "${RUN_LOG}" "${STEPS_FILE}" "$@"; }

run_register_compose() {
  if [[ -f "${REGISTER_ENV}" ]]; then
    docker compose --env-file "${REGISTER_ENV}" -f "${REGISTER_COMPOSE}" "$@"
    return
  fi
  docker compose -f "${REGISTER_COMPOSE}" "$@"
}

collect_diagnostics() {
  log "collecting diagnostics"
  docker compose -f "${LOCAL_TEST_COMPOSE}" ps >"${LOG_DIR}/docker-local-ps.log" 2>&1 || true
  docker compose -f "${LOCAL_TEST_COMPOSE}" logs --no-color >"${LOG_DIR}/docker-local.log" 2>&1 || true
  docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml ps >"${LOG_DIR}/docker-storage-ps.log" 2>&1 || true
  docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml logs --no-color >"${LOG_DIR}/docker-storage.log" 2>&1 || true
  docker logs "${WORKER_CONTAINER_NAME}" >"${LOG_DIR}/worker.log" 2>&1 || true
}

write_summary() {
  python3 "${PY_HELPER}" write-summary-remote \
    --steps-file "${STEPS_FILE}" \
    --summary-file "${SUMMARY_FILE}" \
    --flow-run-id "${FLOW_RUN_ID}" \
    --prefect-api-url "${PREFECT_API_URL}" \
    --work-pool "${PREFECT_WORK_POOL}" \
    --work-queue "${PREFECT_WORK_QUEUE}" \
    --prune-mode "${PRUNE_MODE}"
}

cleanup() {
  if [[ "${BOOTSTRAP_WORKER}" == "true" && "${KEEP_ON_FAIL}" != "true" ]]; then
    docker rm -f "${WORKER_CONTAINER_NAME}" >/dev/null 2>&1 || true
  fi
  write_summary
}
trap cleanup EXIT

must_step() {
  local name="$1"
  shift
  if run_step "${name}" "$@"; then
    return 0
  fi
  collect_diagnostics
  exit 1
}

bootstrap_temp_worker() {
  # This block is isolated for easy removal once production worker validation is fully adopted.
  must_step "worker.remove_existing_temp" bash -lc "docker rm -f '${WORKER_CONTAINER_NAME}' >/dev/null 2>&1 || true"
  must_step "worker.start_temp" docker run -d --rm \
    --name "${WORKER_CONTAINER_NAME}" \
    --network host \
    -e PREFECT_API_URL="${PREFECT_API_URL}" \
    -e PREFECT_CLIENT_CUSTOM_HEADERS="${PREFECT_CUSTOM_HEADERS_JSON}" \
    -e PREFECT_WORK_POOL="${PREFECT_WORK_POOL}" \
    -e STORAGE_GATEWAY_URL="${STORAGE_GATEWAY_URL}" \
    -e STORAGE_GATEWAY_TOKEN="${STORAGE_GATEWAY_TOKEN}" \
    orchestrator-worker:local
  must_step "worker.verify_temp_running" bash -lc "sleep 3 && [[ \"\$(docker inspect --format '{{.State.Running}}' '${WORKER_CONTAINER_NAME}' 2>/dev/null || true)\" == 'true' ]]"
}

log "Remote e2e start: prefect=${PREFECT_API_URL} pool=${PREFECT_WORK_POOL} queue=${PREFECT_WORK_QUEUE}"

PREFECT_CUSTOM_HEADERS_JSON=""
if [[ -n "${PREFECT_CF_ACCESS_CLIENT_ID}" && -n "${PREFECT_CF_ACCESS_CLIENT_SECRET}" ]]; then
  PREFECT_CUSTOM_HEADERS_JSON="$(
    python3 "${PY_HELPER}" build-cf-headers-json \
      --client-id "${PREFECT_CF_ACCESS_CLIENT_ID}" \
      --client-secret "${PREFECT_CF_ACCESS_CLIENT_SECRET}"
  )"
  export PREFECT_CF_ACCESS_CLIENT_ID PREFECT_CF_ACCESS_CLIENT_SECRET
fi

must_step "preflight.tools" bash -lc "command -v docker >/dev/null && command -v curl >/dev/null && command -v python3 >/dev/null"
must_step "preflight.storage_gateway_health" curl -fsS "${STORAGE_GATEWAY_URL%/}/healthz"
MINIO_API_PORT="${MINIO_API_PORT:-9000}"
must_step "preflight.minio_health" curl -fsS "http://127.0.0.1:${MINIO_API_PORT}/minio/health/live"
must_step "build.base_register_worker_images" docker compose -f "${LOCAL_TEST_COMPOSE}" build base-runtime register worker
must_step "prefect.ensure_work_pool" bash -lc "docker run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' -e WORK_POOL='${PREFECT_WORK_POOL}' prefecthq/prefect:3-latest sh -lc 'prefect work-pool inspect \"\$WORK_POOL\" >/dev/null 2>&1 || prefect work-pool create \"\$WORK_POOL\" --type process'"
must_step "register.apply_deployment" bash -lc "run_register_compose() { if [[ -f '${REGISTER_ENV}' ]]; then docker compose --env-file '${REGISTER_ENV}' -f '${REGISTER_COMPOSE}' \"\$@\"; else docker compose -f '${REGISTER_COMPOSE}' \"\$@\"; fi; }; run_register_compose run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' -e PREFECT_WORK_POOL='${PREFECT_WORK_POOL}' -e PREFECT_WORK_QUEUE='${PREFECT_WORK_QUEUE}' register"
must_step "register.verify_deployment" bash -lc "docker run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' prefecthq/prefect:3-latest prefect deployment ls | grep -q 'engine-run/engine-run'"

if [[ "${REGISTER_ONLY}" == "true" ]]; then
  record_step "register.only" "pass" "stopped after register verification"
  log "Register-only mode completed."
  exit 0
fi

if [[ "${BOOTSTRAP_WORKER}" == "true" ]]; then
  bootstrap_temp_worker
else
  record_step "worker.bootstrap_temp" "pass" "skipped (production worker expected)"
fi

must_step "prefect.submit_flow_run" bash -lc "docker run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' prefecthq/prefect:3-latest prefect deployment run 'engine-run/engine-run' -p repo_url='https://github.com/octocat/Hello-World.git' -p ref='master' -p entrypoint='[\"/bin/sh\",\"-lc\",\"echo hello-prefect-remote\"]' > '${LOG_DIR}/prefect-submit.log'"
FLOW_RUN_ID="$(grep -Eo '[0-9a-fA-F-]{36}' "${LOG_DIR}/prefect-submit.log" | head -n1 || true)"
if [[ -z "${FLOW_RUN_ID}" ]]; then
  record_step "prefect.extract_flow_run_id" "fail" "unable to parse flow run id"
  collect_diagnostics
  exit 1
fi
record_step "prefect.extract_flow_run_id" "pass" "${FLOW_RUN_ID}"

must_step "prefect.wait_flow_completion" python3 "${VERIFY_SCRIPT}" prefect-wait-completed --prefect-api-url "${PREFECT_API_URL}" --flow-run-id "${FLOW_RUN_ID}" --timeout-sec "${TIMEOUT_SEC}" --prefect-cf-access-client-id "${PREFECT_CF_ACCESS_CLIENT_ID}" --prefect-cf-access-client-secret "${PREFECT_CF_ACCESS_CLIENT_SECRET}"
must_step "storage.verify_objects" python3 "${VERIFY_SCRIPT}" storage-objects --storage-gateway-url "${STORAGE_GATEWAY_URL}" --storage-gateway-token "${STORAGE_GATEWAY_TOKEN}" --artifact-bucket "${ARTIFACT_BUCKET}" --flow-run-id "${FLOW_RUN_ID}" --attempt 1 --output-json "${LOG_DIR}/storage-objects.json"
must_step "prefect.verify_flush" python3 "${VERIFY_SCRIPT}" flush-verify --prefect-api-url "${PREFECT_API_URL}" --storage-gateway-url "${STORAGE_GATEWAY_URL}" --storage-gateway-token "${STORAGE_GATEWAY_TOKEN}" --flow-run-id "${FLOW_RUN_ID}" --cursor-path "${LOG_DIR}/prefect-flush-cursor.json" --prefect-cf-access-client-id "${PREFECT_CF_ACCESS_CLIENT_ID}" --prefect-cf-access-client-secret "${PREFECT_CF_ACCESS_CLIENT_SECRET}"

if [[ "${PRUNE_MODE}" == "apply" ]]; then
  must_step "prefect.verify_prune" python3 "${VERIFY_SCRIPT}" prune-verify --prefect-api-url "${PREFECT_API_URL}" --flow-run-id "${FLOW_RUN_ID}" --apply --ttl-hours "${PRUNE_TTL_HOURS}" --prefect-cf-access-client-id "${PREFECT_CF_ACCESS_CLIENT_ID}" --prefect-cf-access-client-secret "${PREFECT_CF_ACCESS_CLIENT_SECRET}"
else
  must_step "prefect.verify_prune" python3 "${VERIFY_SCRIPT}" prune-verify --prefect-api-url "${PREFECT_API_URL}" --flow-run-id "${FLOW_RUN_ID}" --ttl-hours "${PRUNE_TTL_HOURS}" --prefect-cf-access-client-id "${PREFECT_CF_ACCESS_CLIENT_ID}" --prefect-cf-access-client-secret "${PREFECT_CF_ACCESS_CLIENT_SECRET}"
fi

log "Remote e2e succeeded: flow_run_id=${FLOW_RUN_ID}"
