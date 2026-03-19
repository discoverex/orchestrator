# Workflow functions for local orchestrator e2e test

compose_local() {
  docker compose -p "${LOCAL_PROJECT_NAME}" -f "${LOCAL_COMPOSE_FILE}" "$@"
}

collect_logs() {
  log "collecting diagnostic logs"
  compose_local ps >"${LOG_DIR}/docker-local-ps.log" 2>&1 || true
  compose_local logs --no-color >"${LOG_DIR}/docker-local.log" 2>&1 || true
  compose_local exec -T worker sh -lc 'env | sort' >"${LOG_DIR}/worker-env.log" 2>&1 || true
  compose_local exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment ls >"${LOG_DIR}/prefect-deployments.log" 2>&1 || true
}

write_summary() {
  PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" \
    uv run python "${PY_HELPER}" write-summary-local \
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

wait_prefect_state_local() {
  local flow_run_id="$1"
  local states="$2"
  local timeout_sec="$3"
  compose_local exec -T \
    -e PREFECT_API_URL=http://127.0.0.1:4200/api \
    -e FLOW_RUN_ID="${flow_run_id}" \
    -e TARGET_STATES="${states}" \
    -e TIMEOUT_SEC="${timeout_sec}" \
    prefect python - <<'PY'
import json
import os
import time
from urllib import request

api_url = os.environ["PREFECT_API_URL"].rstrip("/")
flow_run_id = os.environ["FLOW_RUN_ID"]
target_states = {item.strip().upper() for item in os.environ["TARGET_STATES"].split(",") if item.strip()}
timeout_sec = int(os.environ["TIMEOUT_SEC"])
deadline = time.time() + timeout_sec
terminal_fail = {"FAILED", "CRASHED", "CANCELLED"}

while time.time() < deadline:
    with request.urlopen(f"{api_url}/flow_runs/{flow_run_id}", timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    state_type = str(payload.get("state_type") or "").upper()
    if state_type in target_states:
        print(state_type)
        raise SystemExit(0)
    if state_type in terminal_fail:
        print(state_type)
        raise SystemExit(2)
    time.sleep(2)

print("TIMEOUT")
raise SystemExit(3)
PY
}

verify_prefect_priority_local() {
  local higher_flow_run_id="$1"
  local lower_flow_run_id="$2"
  local timeout_sec="$3"
  compose_local exec -T \
    -e PREFECT_API_URL=http://127.0.0.1:4200/api \
    -e HIGHER_FLOW_RUN_ID="${higher_flow_run_id}" \
    -e LOWER_FLOW_RUN_ID="${lower_flow_run_id}" \
    -e TIMEOUT_SEC="${timeout_sec}" \
    prefect python - <<'PY'
import json
import os
import time
from urllib import request

api_url = os.environ["PREFECT_API_URL"].rstrip("/")
higher_flow_run_id = os.environ["HIGHER_FLOW_RUN_ID"]
lower_flow_run_id = os.environ["LOWER_FLOW_RUN_ID"]
timeout_sec = int(os.environ["TIMEOUT_SEC"])
deadline = time.time() + timeout_sec
running_states = {"RUNNING", "COMPLETED"}
fail_states = {"FAILED", "CRASHED", "CANCELLED"}

def read_state(flow_run_id: str) -> str:
    with request.urlopen(f"{api_url}/flow_runs/{flow_run_id}", timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return str(payload.get("state_type") or "").upper()

while time.time() < deadline:
    higher_state = read_state(higher_flow_run_id)
    lower_state = read_state(lower_flow_run_id)
    if higher_state in fail_states:
        raise SystemExit(f"higher-priority flow run failed early: {higher_state}")
    if lower_state in fail_states:
        raise SystemExit(f"lower-priority flow run failed early: {lower_state}")
    if lower_state in running_states and higher_state not in running_states:
        raise SystemExit("lower-priority flow run advanced before higher-priority flow run")
    if higher_state in running_states and lower_state not in running_states:
        print("priority-ok")
        raise SystemExit(0)
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
    orchestrator-worker-cpu:local \
    /bin/sh -lc "\
      PYTHONPATH=/workspace /opt/venv/bin/python scripts/e2e/shell_python_helpers.py verify-storage-objects \
      --flow-run-id '${FLOW_RUN_ID}' \
      --attempt 1 \
      --storage-api-url 'http://worker-router:8200' \
      --cf-access-client-id '${CF_ACCESS_CLIENT_ID:-}' \
      --cf-access-client-secret '${CF_ACCESS_CLIENT_SECRET:-}' \
      --artifact-bucket '${ARTIFACT_BUCKET}' \
      --presigned-host-header '${STORAGE_DOWNLOAD_HOST_HEADER:-}' \
      --presigned-internal-base-url 'http://minio:9000' \
      --log-dir '/workspace/${LOG_DIR}' \
      ${extra_args[*]}"
}

verify_engine_mlflow_run_to_file() {
  local out_file="$1"
  local run_id
  run_id="$(verify_engine_mlflow_run)"
  echo "${run_id}" | tee "${out_file}"
}

verify_engine_mlflow_run() {
  local scene_id
  local version_id
  scene_id="$(PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" uv run python - "${LOG_DIR}/engine_output.json" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(str(payload.get("scene_id", "")).strip())
PY
)"
  version_id="$(PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" uv run python - "${LOG_DIR}/engine_output.json" <<'PY'
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
scene_id = os.environ["E2E_SCENE_ID"]
version_id = os.environ["E2E_VERSION_ID"]
conn = sqlite3.connect("/tmp/mlflow/mlflow.db")
cur = conn.cursor()
rows = cur.execute(
    "SELECT DISTINCT r.run_uuid FROM runs AS r JOIN params AS p_scene ON p_scene.run_uuid = r.run_uuid AND p_scene.key = 'scene_id' JOIN params AS p_version ON p_version.run_uuid = r.run_uuid AND p_version.key = 'version_id' WHERE r.experiment_id = 1 AND p_scene.value = ? AND p_version.value = ? ORDER BY r.start_time DESC, r.run_uuid DESC LIMIT 1",
    (scene_id, version_id),
).fetchall()
if not rows:
    raise SystemExit(f"no matching MLflow run found in sqlite for scene_id={scene_id} version_id={version_id}")
print(rows[0][0])
PY
}

verify_prefect_flush() {
  local out_json="${LOG_DIR}/prefect-flush.json"
  docker run --rm \
    --network "${LOCAL_PROJECT_NAME}_default" \
    -v "${ROOT_DIR}:/workspace" \
    -w /workspace \
    orchestrator-worker-cpu:local \
    /bin/sh -lc "\
      PREFECT_API_URL=http://prefect:4200/api \
      FLUSH_TARGET_URL=http://worker-router:8200/artifact \
      FLUSH_CURSOR_PATH=/workspace/${LOG_DIR}/prefect-flush-cursor.json \
      PYTHONPATH=src:/workspace /opt/venv/bin/python scripts/ops/prefect_flush_completed.py --once --page-size 100 --max-runs 500 \
      > /workspace/${out_json}"

  PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" \
    uv run python "${PY_HELPER}" verify-flush-output \
    --output-json "${out_json}" \
    --flow-run-id "${FLOW_RUN_ID}"
}

verify_prefect_prune() {
  local out_json="${LOG_DIR}/prefect-prune.json"
  docker run --rm \
    --network "${LOCAL_PROJECT_NAME}_default" \
    -v "${ROOT_DIR}:/workspace" \
    -w /workspace \
    orchestrator-worker-cpu:local \
    /bin/sh -lc "\
      PREFECT_API_URL=http://prefect:4200/api \
      PYTHONPATH=src:/workspace /opt/venv/bin/python scripts/ops/prefect_prune_completed.py --apply --ttl-hours 0 --page-size 200 --max-runs 1000 \
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

build_flow_parameters() {
  local parameters_path="${LOG_DIR}/flow-parameters.json"
  if [[ "${MODE}" == "core" ]]; then
    PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" uv run python - <<'PY' >"${parameters_path}"
import json
payload = {
    "run_mode": "repo",
    "engine": "dummy-engine",
    "repo_url": "tests/fixtures/dummy_engine_repo",
    "ref": "main",
    "flow_entrypoint": "src/dummy_engine/prefect_flow.py:dummy_engine_flow",
    "config": None, "job_name": "local-e2e-dummy", "inputs": {"scene_id": "local-e2e-scene", "version_id": "attempt-1"}, "env": {}, "outputs_prefix": None,
}
print(json.dumps(payload, ensure_ascii=True))
PY
    echo "${parameters_path}"
    return
  fi

  local profile="local-tiny-cpu"
  local extra_args=()
  if [[ "${MODE}" != "core" ]]; then
    extra_args+=(--mlflow-tracking-uri "${ENGINE_MLFLOW_TRACKING_URI}" --mlflow-s3-endpoint-url "${ENGINE_MLFLOW_S3_ENDPOINT_URL}" --aws-access-key-id "${ENGINE_AWS_ACCESS_KEY_ID}" --aws-secret-access-key "${ENGINE_AWS_SECRET_ACCESS_KEY}" --artifact-bucket "${ARTIFACT_BUCKET}")
  fi
  uv run python "${ENGINE_JOB_SCRIPT}" --dry-run --run-mode inline --entrypoint-shell-command "tmpdir=\$(mktemp -d /tmp/discoverex-engine-XXXXXX) && tar -C ${ENGINE_REPO_URL_CONTAINER} --exclude=.git --exclude=.venv --exclude=.cache --exclude=.ruff_cache -cf - . | tar -C \"\$tmpdir\" -xf - && cd \"\$tmpdir\" && PYTHONPATH=src python -m discoverex.orchestrator_contract.launcher" --execution-profile "${profile}" --command generate --background-asset-ref "${ENGINE_BACKGROUND_ASSET_REF}" "${extra_args[@]}" >"${parameters_path}"
  PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" uv run python - "${parameters_path}" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
engine_run = payload.pop("engine_run", None)
if not isinstance(engine_run, dict):
    raise SystemExit("generated parameters missing engine_run payload")
payload["inputs"] = engine_run
env = payload.get("env", {})
env["MLFLOW_TRACKING_PROXY_URL"] = "http://worker-router:8200/mlflow"
payload["env"] = env
path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
PY
  echo "${parameters_path}"
}

submit_prefect_run() {
  local parameters_path="$1"
  PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" \
    PREFECT_API_URL="http://127.0.0.1:24200/api" \
    uv run python "${ROOT_DIR}/scripts/ops/prefect_submit_router.py" \
    --strict-priority true \
    --fixed-deployment "${TARGET_DEPLOYMENT_NAME}" \
    --colab-deployment "${TARGET_DEPLOYMENT_NAME}" \
    --fixed-queue "gpu-fixed" \
    --colab-queue "gpu-fixed" \
    --parameters-file "${parameters_path}" \
    | tee "${LOG_DIR}/prefect-submit.log"
}
