#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

REGISTER_ENV="${ROOT_DIR}/infra/stacks/register/.env"
REGISTER_COMPOSE="${ROOT_DIR}/infra/stacks/register/docker-compose.yml"
VERIFY_SCRIPT="${ROOT_DIR}/scripts/e2e/verify_remote_chain.py"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

if [[ -f "${ROOT_DIR}/infra/stacks/storage-node/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/infra/stacks/storage-node/.env"
  set +a
fi

PREFECT_API_URL="${PREFECT_API_URL:-}"
PREFECT_WORK_POOL="${PREFECT_WORK_POOL:-colab-gpu}"
PREFECT_WORK_QUEUE="${PREFECT_WORK_QUEUE:-default}"
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
  scripts/e2e/remote_prefect_storage_e2e.sh --prefect-api-url URL [options]

Options:
  --prefect-api-url URL         Remote Prefect API URL (e.g. https://<host>/api)
  --work-pool NAME              Prefect work pool name (default: colab-gpu)
  --work-queue NAME             Prefect work queue name (default: default)
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
ARTIFACT_DIR="artifacts/e2e/${STAMP}-remote"
LOG_DIR="${ARTIFACT_DIR}/logs"
RUN_LOG="${LOG_DIR}/run.log"
STEPS_FILE="${ARTIFACT_DIR}/steps.tsv"
SUMMARY_FILE="${ARTIFACT_DIR}/summary.json"
mkdir -p "${LOG_DIR}"
touch "${STEPS_FILE}"

log() {
  echo "[$(date +%H:%M:%S)] $*" | tee -a "${RUN_LOG}"
}

record_step() {
  local name="$1"
  local status="$2"
  local message="$3"
  printf "%s\t%s\t%s\n" "$name" "$status" "$message" >> "${STEPS_FILE}"
}

run_step() {
  local name="$1"
  shift
  log "STEP ${name}"
  if "$@" >>"${RUN_LOG}" 2>&1; then
    record_step "${name}" "pass" "ok"
    return 0
  fi
  record_step "${name}" "fail" "failed (see run.log)"
  return 1
}

run_register_compose() {
  if [[ -f "${REGISTER_ENV}" ]]; then
    docker compose --env-file "${REGISTER_ENV}" -f "${REGISTER_COMPOSE}" "$@"
    return
  fi
  docker compose -f "${REGISTER_COMPOSE}" "$@"
}

collect_diagnostics() {
  log "collecting diagnostics"
  docker compose -f docker-compose.local.yml ps >"${LOG_DIR}/docker-local-ps.log" 2>&1 || true
  docker compose -f docker-compose.local.yml logs --no-color >"${LOG_DIR}/docker-local.log" 2>&1 || true
  docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml ps >"${LOG_DIR}/docker-storage-ps.log" 2>&1 || true
  docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml logs --no-color >"${LOG_DIR}/docker-storage.log" 2>&1 || true
  docker logs "${WORKER_CONTAINER_NAME}" >"${LOG_DIR}/worker.log" 2>&1 || true
}

write_summary() {
  python3 - <<'PY' "${STEPS_FILE}" "${SUMMARY_FILE}" "${FLOW_RUN_ID}" "${PREFECT_API_URL}" "${PREFECT_WORK_POOL}" "${PREFECT_WORK_QUEUE}" "${PRUNE_MODE}"
import json
import sys
from pathlib import Path

steps_file = Path(sys.argv[1])
summary_file = Path(sys.argv[2])
flow_run_id = sys.argv[3]
prefect_api_url = sys.argv[4]
work_pool = sys.argv[5]
work_queue = sys.argv[6]
prune_mode = sys.argv[7]

steps = []
for raw in steps_file.read_text(encoding="utf-8").splitlines():
    if not raw.strip():
        continue
    name, status, message = raw.split("\t", 2)
    steps.append({"name": name, "status": status, "message": message})

summary = {
    "ok": all(s["status"] == "pass" for s in steps),
    "flow_run_id": flow_run_id or None,
    "prefect_api_url": prefect_api_url,
    "work_pool": work_pool,
    "work_queue": work_queue,
    "prune_mode": prune_mode,
    "steps": steps,
}
summary_file.parent.mkdir(parents=True, exist_ok=True)
summary_file.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
PY
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
  must_step "temp-worker-remove-existing" bash -lc "docker rm -f '${WORKER_CONTAINER_NAME}' >/dev/null 2>&1 || true"
  must_step "temp-worker-start" docker run -d --rm \
    --name "${WORKER_CONTAINER_NAME}" \
    --network host \
    -e PREFECT_API_URL="${PREFECT_API_URL}" \
    -e PREFECT_CLIENT_CUSTOM_HEADERS="${PREFECT_CUSTOM_HEADERS_JSON}" \
    -e PREFECT_WORK_POOL="${PREFECT_WORK_POOL}" \
    -e STORAGE_GATEWAY_URL="${STORAGE_GATEWAY_URL}" \
    -e STORAGE_GATEWAY_TOKEN="${STORAGE_GATEWAY_TOKEN}" \
    orchestrator-worker:local
  must_step "temp-worker-running" bash -lc "sleep 3 && [[ \"\$(docker inspect --format '{{.State.Running}}' '${WORKER_CONTAINER_NAME}' 2>/dev/null || true)\" == 'true' ]]"
}

log "Remote e2e start: prefect=${PREFECT_API_URL} pool=${PREFECT_WORK_POOL} queue=${PREFECT_WORK_QUEUE}"

PREFECT_CUSTOM_HEADERS_JSON=""
if [[ -n "${PREFECT_CF_ACCESS_CLIENT_ID}" && -n "${PREFECT_CF_ACCESS_CLIENT_SECRET}" ]]; then
  PREFECT_CUSTOM_HEADERS_JSON="$(
    python3 - <<'PY' "${PREFECT_CF_ACCESS_CLIENT_ID}" "${PREFECT_CF_ACCESS_CLIENT_SECRET}"
import json
import sys

print(
    json.dumps(
        {
            "CF-Access-Client-Id": sys.argv[1],
            "CF-Access-Client-Secret": sys.argv[2],
        },
        ensure_ascii=True,
    )
)
PY
  )"
  export PREFECT_CF_ACCESS_CLIENT_ID PREFECT_CF_ACCESS_CLIENT_SECRET
fi

must_step "preflight-tools" bash -lc "command -v docker >/dev/null && command -v curl >/dev/null && command -v python3 >/dev/null"
must_step "preflight-storage-gateway-health" curl -fsS "${STORAGE_GATEWAY_URL%/}/healthz"
MINIO_API_PORT="${MINIO_API_PORT:-9000}"
must_step "preflight-minio-health" curl -fsS "http://127.0.0.1:${MINIO_API_PORT}/minio/health/live"
must_step "build-register-worker-images" docker compose -f docker-compose.local.yml build base-runtime register worker
must_step "ensure-work-pool" bash -lc "docker run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' -e WORK_POOL='${PREFECT_WORK_POOL}' prefecthq/prefect:3-latest sh -lc 'prefect work-pool inspect \"\$WORK_POOL\" >/dev/null 2>&1 || prefect work-pool create \"\$WORK_POOL\" --type process'"
must_step "register-deployment" bash -lc "run_register_compose() { if [[ -f '${REGISTER_ENV}' ]]; then docker compose --env-file '${REGISTER_ENV}' -f '${REGISTER_COMPOSE}' \"\$@\"; else docker compose -f '${REGISTER_COMPOSE}' \"\$@\"; fi; }; run_register_compose run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' -e PREFECT_WORK_POOL='${PREFECT_WORK_POOL}' -e PREFECT_WORK_QUEUE='${PREFECT_WORK_QUEUE}' register"
must_step "verify-deployment" bash -lc "docker run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' prefecthq/prefect:3-latest prefect deployment ls | grep -q 'engine-run/engine-run'"

if [[ "${REGISTER_ONLY}" == "true" ]]; then
  record_step "register-only" "pass" "stopped after register verification"
  log "Register-only mode completed."
  exit 0
fi

if [[ "${BOOTSTRAP_WORKER}" == "true" ]]; then
  bootstrap_temp_worker
else
  record_step "temp-worker-bootstrap" "pass" "skipped (production worker expected)"
fi

must_step "submit-flow-run" bash -lc "docker run --rm -e PREFECT_API_URL='${PREFECT_API_URL}' -e PREFECT_CLIENT_CUSTOM_HEADERS='${PREFECT_CUSTOM_HEADERS_JSON}' prefecthq/prefect:3-latest prefect deployment run 'engine-run/engine-run' -p repo_url='https://github.com/octocat/Hello-World.git' -p ref='master' -p entrypoint='[\"/bin/sh\",\"-lc\",\"echo hello-prefect-remote\"]' > '${LOG_DIR}/prefect-submit.log'"
FLOW_RUN_ID="$(grep -Eo '[0-9a-fA-F-]{36}' "${LOG_DIR}/prefect-submit.log" | head -n1 || true)"
if [[ -z "${FLOW_RUN_ID}" ]]; then
  record_step "extract-flow-run-id" "fail" "unable to parse flow run id"
  collect_diagnostics
  exit 1
fi
record_step "extract-flow-run-id" "pass" "${FLOW_RUN_ID}"

must_step "wait-flow-completion" python3 "${VERIFY_SCRIPT}" prefect-wait-completed --prefect-api-url "${PREFECT_API_URL}" --flow-run-id "${FLOW_RUN_ID}" --timeout-sec "${TIMEOUT_SEC}" --prefect-cf-access-client-id "${PREFECT_CF_ACCESS_CLIENT_ID}" --prefect-cf-access-client-secret "${PREFECT_CF_ACCESS_CLIENT_SECRET}"
must_step "verify-storage-objects" python3 "${VERIFY_SCRIPT}" storage-objects --storage-gateway-url "${STORAGE_GATEWAY_URL}" --storage-gateway-token "${STORAGE_GATEWAY_TOKEN}" --artifact-bucket "${ARTIFACT_BUCKET}" --flow-run-id "${FLOW_RUN_ID}" --attempt 1 --output-json "${LOG_DIR}/storage-objects.json"
must_step "verify-prefect-flush" python3 "${VERIFY_SCRIPT}" flush-verify --prefect-api-url "${PREFECT_API_URL}" --storage-gateway-url "${STORAGE_GATEWAY_URL}" --storage-gateway-token "${STORAGE_GATEWAY_TOKEN}" --flow-run-id "${FLOW_RUN_ID}" --cursor-path "${LOG_DIR}/prefect-flush-cursor.json" --prefect-cf-access-client-id "${PREFECT_CF_ACCESS_CLIENT_ID}" --prefect-cf-access-client-secret "${PREFECT_CF_ACCESS_CLIENT_SECRET}"

if [[ "${PRUNE_MODE}" == "apply" ]]; then
  must_step "verify-prefect-prune" python3 "${VERIFY_SCRIPT}" prune-verify --prefect-api-url "${PREFECT_API_URL}" --flow-run-id "${FLOW_RUN_ID}" --apply --ttl-hours "${PRUNE_TTL_HOURS}" --prefect-cf-access-client-id "${PREFECT_CF_ACCESS_CLIENT_ID}" --prefect-cf-access-client-secret "${PREFECT_CF_ACCESS_CLIENT_SECRET}"
else
  must_step "verify-prefect-prune" python3 "${VERIFY_SCRIPT}" prune-verify --prefect-api-url "${PREFECT_API_URL}" --flow-run-id "${FLOW_RUN_ID}" --ttl-hours "${PRUNE_TTL_HOURS}" --prefect-cf-access-client-id "${PREFECT_CF_ACCESS_CLIENT_ID}" --prefect-cf-access-client-secret "${PREFECT_CF_ACCESS_CLIENT_SECRET}"
fi

log "Remote e2e succeeded: flow_run_id=${FLOW_RUN_ID}"
