# Workflow functions for remote prefect storage e2e test

: "${RUNTIME_ROOT:=${ROOT_DIR}/../runtime}"
: "${WORKER_RUNTIME_DIR:=${RUNTIME_ROOT}/worker}"
: "${WORKER_CHECKPOINT_DIR:=${RUNTIME_ROOT}/worker/checkpoints}"
: "${WORKER_CACHE_DIR:=${RUNTIME_ROOT}/worker/cache}"

normalize_public_git_url() {
  local raw="$1"
  if [[ "$raw" =~ ^git@github\.com:(.+)$ ]]; then
    printf 'https://github.com/%s\n' "${BASH_REMATCH[1]}"
    return
  fi
  printf '%s\n' "$raw"
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
  docker compose -f "${LOCAL_TEST_COMPOSE}" ps >"${LOG_DIR}/docker-local-ps.log" 2>&1 || true
  docker compose -f "${LOCAL_TEST_COMPOSE}" logs --no-color >"${LOG_DIR}/docker-local.log" 2>&1 || true
  docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml ps >"${LOG_DIR}/docker-storage-ps.log" 2>&1 || true
  docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml logs --no-color >"${LOG_DIR}/docker-storage.log" 2>&1 || true
  docker logs "${WORKER_CONTAINER_NAME}" >"${LOG_DIR}/worker.log" 2>&1 || true
}

write_summary() {
  PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}" uv run python "${PY_HELPER}" write-summary-remote \
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

build_flow_parameters() {
  if [[ -n "${FLOW_PARAMETERS_JSON}" ]]; then
    printf '%s' "${FLOW_PARAMETERS_JSON}" >"${LOG_DIR}/flow-parameters.json"
    return 0
  fi
  if [[ -n "${FLOW_PARAMETERS_FILE}" ]]; then
    [[ ! -f "${FLOW_PARAMETERS_FILE}" ]] && { echo "parameters file not found: ${FLOW_PARAMETERS_FILE}" >&2; return 1; }
    cp "${FLOW_PARAMETERS_FILE}" "${LOG_DIR}/flow-parameters.json"
    return 0
  fi
  [[ -z "${ENGINE_MLFLOW_TRACKING_URI}" ]] && { echo "missing MLFLOW_TRACKING_URI" >&2; return 1; }
  [[ -z "${ENGINE_MLFLOW_S3_ENDPOINT_URL}" ]] && { echo "missing MLFLOW_S3_ENDPOINT_URL" >&2; return 1; }
  [[ -z "${ENGINE_AWS_ACCESS_KEY_ID}" || -z "${ENGINE_AWS_SECRET_ACCESS_KEY}" ]] && { echo "missing MinIO credentials" >&2; return 1; }
  python3 "${ENGINE_JOB_SCRIPT}" --dry-run --execution-profile "${ENGINE_EXECUTION_PROFILE}" --command generate --repo-url "${ENGINE_REPO_URL}" --ref "${ENGINE_REPO_REF}" --background-asset-ref "${ENGINE_BACKGROUND_ASSET_REF}" --mlflow-tracking-uri "${ENGINE_MLFLOW_TRACKING_URI}" --mlflow-s3-endpoint-url "${ENGINE_MLFLOW_S3_ENDPOINT_URL}" --aws-access-key-id "${ENGINE_AWS_ACCESS_KEY_ID}" --aws-secret-access-key "${ENGINE_AWS_SECRET_ACCESS_KEY}" --artifact-bucket "${ARTIFACT_BUCKET}" --cf-access-client-id "${CF_ACCESS_CLIENT_ID:-}" --cf-access-client-secret "${CF_ACCESS_CLIENT_SECRET:-}" >"${LOG_DIR}/flow-parameters.json"
}

bootstrap_temp_worker() {
  mkdir -p "${WORKER_RUNTIME_DIR}" "${WORKER_CHECKPOINT_DIR}" "${WORKER_CACHE_DIR}"
  chmod 0777 "${WORKER_RUNTIME_DIR}" "${WORKER_CHECKPOINT_DIR}" "${WORKER_CACHE_DIR}" || true
  must_step "worker.remove_existing_temp" bash -lc "docker rm -f '${WORKER_CONTAINER_NAME}' >/dev/null 2>&1 || true"
  must_step "worker.start_temp" docker run -d --rm --name "${WORKER_CONTAINER_NAME}" --network host -e PREFECT_API_URL="${PREFECT_API_URL}" -e PREFECT_CLIENT_CUSTOM_HEADERS="${PREFECT_CUSTOM_HEADERS_JSON}" -e PREFECT_WORK_POOL="${PREFECT_WORK_POOL}" -e PREFECT_WORK_QUEUE="${PREFECT_WORK_QUEUE}" -e STORAGE_API_URL="${STORAGE_API_URL}" -e CF_ACCESS_CLIENT_ID="${CF_ACCESS_CLIENT_ID}" -e CF_ACCESS_CLIENT_SECRET="${CF_ACCESS_CLIENT_SECRET}" -e ORCHESTRATOR_CHECKPOINT_DIR=/var/lib/orchestrator/checkpoints -e ORCH_CACHE_DIR=/var/lib/orchestrator/cache -v "${WORKER_RUNTIME_DIR}:/var/lib/orchestrator" orchestrator-worker:local
  must_step "worker.verify_temp_running" bash -lc "sleep 3 && [[ \"\$(docker inspect --format '{{.State.Running}}' '${WORKER_CONTAINER_NAME}' 2>/dev/null || true)\" == 'true' ]]"
}
