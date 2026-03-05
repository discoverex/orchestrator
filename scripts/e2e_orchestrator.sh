#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

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

if [[ "$MODE" != "core" && "$MODE" != "mlflow" && "$MODE" != "full" ]]; then
  echo "--mode must be one of: core, mlflow, full" >&2
  exit 2
fi

if ! [[ "$TIMEOUT_SEC" =~ ^[0-9]+$ ]]; then
  echo "--timeout-sec must be an integer" >&2
  exit 2
fi

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
ARTIFACT_DIR="artifacts/e2e/${STAMP}-${MODE}"
LOG_DIR="${ARTIFACT_DIR}/logs"
SUMMARY_FILE="${ARTIFACT_DIR}/summary.json"
STEPS_FILE="${ARTIFACT_DIR}/steps.tsv"
RUN_LOG="${LOG_DIR}/run.log"
mkdir -p "${LOG_DIR}"

PREFECT_API_URL="${PREFECT_API_URL:-http://127.0.0.1:14200/api}"
PREFECT_WORK_POOL="${PREFECT_WORK_POOL:-colab-gpu}"
STORAGE_GATEWAY_URL="${STORAGE_GATEWAY_URL:-http://127.0.0.1:18100}"
STORAGE_GATEWAY_TOKEN="${STORAGE_GATEWAY_TOKEN:-dev-storage-token}"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-orchestrator-artifacts}"
export PREFECT_API_URL PREFECT_WORK_POOL STORAGE_GATEWAY_URL STORAGE_GATEWAY_TOKEN ARTIFACT_BUCKET

FLOW_RUN_ID=""
MLFLOW_RUN_ID=""

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
    record_step "$name" "pass" "ok"
  else
    record_step "$name" "fail" "failed (see run.log)"
    return 1
  fi
}

require_env() {
  local key="$1"
  if [[ -z "${!key:-}" ]]; then
    log "missing required env: ${key}"
    record_step "env:${key}" "fail" "missing required env"
    exit 1
  fi
}

collect_logs() {
  log "collecting diagnostic logs"
  docker compose -f docker-compose.local.yml ps >"${LOG_DIR}/docker-local-ps.log" 2>&1 || true
  docker compose -f docker-compose.local.yml logs --no-color >"${LOG_DIR}/docker-local.log" 2>&1 || true
  docker compose --env-file infra/storage-node/.env -f infra/storage-node/docker-compose.yml ps >"${LOG_DIR}/docker-storage-ps.log" 2>&1 || true
  docker compose --env-file infra/storage-node/.env -f infra/storage-node/docker-compose.yml logs --no-color >"${LOG_DIR}/docker-storage.log" 2>&1 || true
  docker compose -f docker-compose.local.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment ls >"${LOG_DIR}/prefect-deployments.log" 2>&1 || true
}

write_summary() {
  python3 - <<'PY' "${STEPS_FILE}" "${SUMMARY_FILE}" "${MODE}" "${FLOW_RUN_ID}" "${MLFLOW_RUN_ID}"
import json
import sys
from pathlib import Path

steps_file = Path(sys.argv[1])
summary_file = Path(sys.argv[2])
mode = sys.argv[3]
flow_run_id = sys.argv[4]
mlflow_run_id = sys.argv[5]

steps = []
if steps_file.exists():
    for raw in steps_file.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        name, status, message = raw.split("\t", 2)
        steps.append({"name": name, "status": status, "message": message})

summary = {
    "mode": mode,
    "ok": all(s["status"] == "pass" for s in steps),
    "flow_run_id": flow_run_id or None,
    "mlflow_run_id": mlflow_run_id or None,
    "steps": steps,
}
summary_file.parent.mkdir(parents=True, exist_ok=True)
summary_file.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
PY
}

cleanup() {
  if [[ "${KEEP_ON_FAIL}" != "true" ]]; then
    docker compose -f docker-compose.local.yml down >/dev/null 2>&1 || true
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
  python3 - <<'PY' "${PREFECT_API_URL}" "${FLOW_RUN_ID}" "${TIMEOUT_SEC}"
import json
import sys
import time
from urllib import request

api_url = sys.argv[1].rstrip("/")
run_id = sys.argv[2]
timeout = int(sys.argv[3])
terminal_success = {"COMPLETED"}
terminal_fail = {"FAILED", "CRASHED", "CANCELLED"}

deadline = time.time() + timeout
while time.time() < deadline:
    req = request.Request(f"{api_url}/flow_runs/{run_id}", method="GET")
    with request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    state_type = (payload.get("state_type") or payload.get("state", {}).get("type") or "").upper()
    if state_type in terminal_success:
        print("COMPLETED")
        sys.exit(0)
    if state_type in terminal_fail:
        print(state_type)
        sys.exit(2)
    time.sleep(2)

print("TIMEOUT")
sys.exit(3)
PY
}

verify_storage_objects() {
  python3 - <<'PY' "${FLOW_RUN_ID}" "${STORAGE_GATEWAY_URL}" "${STORAGE_GATEWAY_TOKEN}" "${ARTIFACT_BUCKET}" "${LOG_DIR}"
import json
import sys
from pathlib import Path
from urllib import request

flow_run_id = sys.argv[1]
gateway = sys.argv[2].rstrip("/")
token = sys.argv[3]
bucket = sys.argv[4]
log_dir = Path(sys.argv[5])
attempt = 1

uris = {
    "stdout": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/stdout.log",
    "stderr": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/stderr.log",
    "result": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/result.json",
    "manifest": f"s3://{bucket}/jobs/{flow_run_id}/attempt-{attempt}/artifacts.json",
}

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

for object_uri in uris.values():
    body = json.dumps({"object_uri": object_uri}).encode("utf-8")
    req = request.Request(f"{gateway}/v1/object/head", method="POST", data=body, headers=headers)
    with request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("exists"):
        raise SystemExit(f"missing object: {object_uri}")

manifest_req = json.dumps({
    "flow_run_id": flow_run_id,
    "attempt": attempt,
    "kind": "manifest",
    "filename": "artifacts.json",
}).encode("utf-8")
req = request.Request(f"{gateway}/v1/presign/get", method="POST", data=manifest_req, headers=headers)
with request.urlopen(req, timeout=10) as resp:
    manifest_link = json.loads(resp.read().decode("utf-8"))

with request.urlopen(manifest_link["url"], timeout=15) as resp:
    manifest = json.loads(resp.read().decode("utf-8"))

if manifest.get("flow_run_id") != flow_run_id:
    raise SystemExit("manifest flow_run_id mismatch")
if int(manifest.get("attempt", -1)) != attempt:
    raise SystemExit("manifest attempt mismatch")

rows = manifest.get("artifacts", [])
kinds = {row.get("kind"): row.get("object_uri") for row in rows if isinstance(row, dict)}
for kind in ("stdout", "stderr", "result"):
    if kinds.get(kind) != uris[kind]:
        raise SystemExit(f"manifest {kind} uri mismatch")

(log_dir / "flow_uris.json").write_text(json.dumps(uris, ensure_ascii=True, indent=2), encoding="utf-8")
PY
}

create_and_verify_mlflow_tags() {
  python3 - <<'PY' "${MLFLOW_TRACKING_URI}" "${FLOW_RUN_ID}" "${LOG_DIR}" "${CF_ACCESS_CLIENT_ID:-}" "${CF_ACCESS_CLIENT_SECRET:-}"
import json
import sys
from pathlib import Path
from urllib import parse, request, error

tracking_uri = sys.argv[1].rstrip("/")
flow_run_id = sys.argv[2]
log_dir = Path(sys.argv[3])
cf_access_client_id = sys.argv[4]
cf_access_client_secret = sys.argv[5]
flow_uris = json.loads((log_dir / "flow_uris.json").read_text(encoding="utf-8"))

base_headers = {
    "Content-Type": "application/json",
    "User-Agent": "orchestrator-e2e/1.0",
}
if cf_access_client_id and cf_access_client_secret:
    base_headers["CF-Access-Client-Id"] = cf_access_client_id
    base_headers["CF-Access-Client-Secret"] = cf_access_client_secret

def post(path: str, payload: dict) -> dict:
    req = request.Request(
        f"{tracking_uri}{path}",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers=base_headers,
    )
    with request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get(path: str, query: dict) -> dict:
    qs = parse.urlencode(query)
    req = request.Request(f"{tracking_uri}{path}?{qs}", method="GET", headers=base_headers)
    with request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

experiment_id = "0"

try:
    run = post("/api/2.0/mlflow/runs/create", {"experiment_id": experiment_id, "start_time": 0, "tags": []})
except error.HTTPError as exc:
    raise SystemExit(f"mlflow runs/create failed: HTTP {exc.code}") from exc
run_id = run["run"]["info"]["run_id"]

tags = {
    "artifact_manifest_uri": flow_uris["manifest"],
    "artifact_stdout_uri": flow_uris["stdout"],
    "artifact_stderr_uri": flow_uris["stderr"],
    "artifact_result_uri": flow_uris["result"],
    "e2e_flow_run_id": flow_run_id,
}
for key, value in tags.items():
    post("/api/2.0/mlflow/runs/set-tag", {"run_id": run_id, "key": key, "value": value})

fetched = get("/api/2.0/mlflow/runs/get", {"run_id": run_id})
rows = fetched["run"]["data"].get("tags", [])
values = {row["key"]: row["value"] for row in rows}
for key, value in tags.items():
    if values.get(key) != value:
        raise SystemExit(f"mlflow tag mismatch: {key}")

print(run_id)
PY
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

check_full_external_access() {
  require_env MLFLOW_PUBLIC_URL
  require_env CF_ACCESS_CLIENT_ID
  require_env CF_ACCESS_CLIENT_SECRET

  local unauth_code
  unauth_code="$(curl -sS -o /dev/null -w "%{http_code}" "${MLFLOW_PUBLIC_URL}")"
  if [[ "${unauth_code}" == "200" ]]; then
    return 1
  fi

  local auth_code
  auth_code="$(
    curl -sS -o /dev/null -w "%{http_code}" \
      -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
      -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
      -H "Content-Type: application/json" \
      -d '{"max_results": 1}' \
      "${MLFLOW_PUBLIC_URL%/}/api/2.0/mlflow/experiments/search"
  )"
  [[ "${auth_code}" == "200" ]]
}

uri_host() {
  local uri="$1"
  python3 - <<'PY' "${uri}"
import sys
from urllib.parse import urlsplit

host = urlsplit(sys.argv[1]).hostname or ""
if not host:
    raise SystemExit("unable to parse host from uri")
print(host)
PY
}

verify_full_prereqs() {
  require_env MLFLOW_TRACKING_URI
  require_env MLFLOW_PUBLIC_URL
  require_env CF_ACCESS_CLIENT_ID
  require_env CF_ACCESS_CLIENT_SECRET

  local tracking_host
  local public_host
  tracking_host="$(uri_host "${MLFLOW_TRACKING_URI}")"
  public_host="$(uri_host "${MLFLOW_PUBLIC_URL}")"

  getent ahosts "${tracking_host}" >/dev/null
  getent ahosts "${public_host}" >/dev/null
}

run_step "build-and-up-local-services" docker compose -f docker-compose.local.yml up -d --build minio prefect storage-gateway worker
run_step "wait-minio-health" wait_health orchestrator-minio 90
run_step "wait-prefect-health" wait_health orchestrator-prefect 90
run_step "wait-gateway-health" wait_health orchestrator-storage-gateway-local 90
run_step "ensure-work-pool" bash -lc "docker compose -f docker-compose.local.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect work-pool create ${PREFECT_WORK_POOL} --type process >/dev/null 2>&1 || true"

run_step "register-deployment" docker compose -f docker-compose.local.yml run --rm register
run_step "verify-deployment" bash -lc "docker compose -f docker-compose.local.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment ls | grep -q 'engine-run/engine-run'"

run_step "submit-flow-run" bash -lc "docker compose -f docker-compose.local.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment run 'engine-run/engine-run' -p repo_url='https://github.com/octocat/Hello-World.git' -p ref='master' -p entrypoint='[\"/bin/sh\",\"-lc\",\"echo hello-prefect\"]' > '${LOG_DIR}/prefect-submit.log'"
FLOW_RUN_ID="$(grep -Eo '[0-9a-fA-F-]{36}' "${LOG_DIR}/prefect-submit.log" | head -n1 || true)"
if [[ -z "${FLOW_RUN_ID}" ]]; then
  record_step "extract-flow-run-id" "fail" "unable to parse flow run id"
  collect_logs
  exit 1
fi
record_step "extract-flow-run-id" "pass" "${FLOW_RUN_ID}"

if poll_prefect_completion >>"${RUN_LOG}" 2>&1; then
  record_step "wait-flow-completion" "pass" "completed"
else
  record_step "wait-flow-completion" "fail" "did not complete"
  collect_logs
  exit 1
fi

if verify_storage_objects >>"${RUN_LOG}" 2>&1; then
  record_step "verify-storage-objects" "pass" "stdout/stderr/result/manifest present"
else
  record_step "verify-storage-objects" "fail" "missing object or invalid manifest"
  collect_logs
  exit 1
fi

if [[ "${MODE}" == "full" ]]; then
  if verify_full_prereqs >>"${RUN_LOG}" 2>&1; then
    record_step "verify-full-prereqs" "pass" "env present + DNS resolved"
  else
    record_step "verify-full-prereqs" "fail" "missing env or DNS not resolved"
    collect_logs
    exit 1
  fi
fi

if [[ "${MODE}" == "mlflow" || "${MODE}" == "full" ]]; then
  require_env MLFLOW_TRACKING_URI
  if check_mlflow_tracking_access >>"${RUN_LOG}" 2>&1; then
    record_step "verify-mlflow-tracking-access" "pass" "mlflow API reachable"
  else
    record_step "verify-mlflow-tracking-access" "fail" "mlflow API returned non-200"
    collect_logs
    exit 1
  fi
  if MLFLOW_RUN_ID="$(create_and_verify_mlflow_tags 2>>"${RUN_LOG}")"; then
    record_step "verify-mlflow-tags" "pass" "${MLFLOW_RUN_ID}"
  else
    record_step "verify-mlflow-tags" "fail" "mlflow create/get tag check failed"
    collect_logs
    exit 1
  fi
fi

if [[ "${MODE}" == "full" ]]; then
  if check_full_external_access >>"${RUN_LOG}" 2>&1; then
    record_step "verify-full-external-access" "pass" "unauth blocked + token auth ok"
  else
    record_step "verify-full-external-access" "fail" "external access policy check failed"
    collect_logs
    exit 1
  fi
fi

log "E2E succeeded: mode=${MODE} flow_run_id=${FLOW_RUN_ID} mlflow_run_id=${MLFLOW_RUN_ID:-N/A}"
