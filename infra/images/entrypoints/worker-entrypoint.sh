#!/usr/bin/env sh
set -eu

log() {
  printf '%s | worker-entrypoint | %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

if [ "${PREFECT_CLIENT_CUSTOM_HEADERS:-}" = "" ]; then
  unset PREFECT_CLIENT_CUSTOM_HEADERS || true
fi

eval "$(
  /opt/venv/bin/python -c \
  'from common.prefect.client_env import shell_exports; print(shell_exports(default_queue="gpu-fixed"))'
)"

POOL="${PREFECT_WORK_POOL:-gpu-pool}"
PRIMARY_QUEUE="${PREFECT_WORK_QUEUE:-gpu-fixed}"
BATCH_QUEUE="${PREFECT_BATCH_WORK_QUEUE:-${PRIMARY_QUEUE}-batch}"
WORK_QUEUES="${PREFECT_WORK_QUEUES:-${PRIMARY_QUEUE},${BATCH_QUEUE}}"
WORKER_LIMIT="${PREFECT_WORKER_LIMIT:-1}"
WORKER_RUNTIME_DIR="${ORCH_WORKER_RUNTIME_DIR:-/var/lib/orchestrator}"
CACHE_DIR="${ORCH_CACHE_DIR:-${WORKER_RUNTIME_DIR}/cache}"
CHECKPOINT_DIR="${ORCHESTRATOR_CHECKPOINT_DIR:-/var/lib/orchestrator/checkpoints}"
REPO_CACHE_DIR="${ORCH_REPO_CACHE_DIR:-${CACHE_DIR}/repo}"
MODEL_CACHE_DIR="${ORCH_MODEL_CACHE_DIR:-${CACHE_DIR}/models}"
WORKER_ROUTER_PORT="${WORKER_ROUTER_PORT:-8200}"
REMOTE_PREFECT_API_URL="${PREFECT_API_URL:-}"
REMOTE_MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-${STORAGE_API_URL%/}/mlflow}"
PREFECT_UPSTREAM_BASE_URL="${REMOTE_PREFECT_API_URL%/api}"
SUMMARY="$(
  /opt/venv/bin/python -m common.prefect.client_env summary --default-queue "gpu-fixed"
)"

export ORCH_WORKER_RUNTIME_DIR="${WORKER_RUNTIME_DIR}"
export ORCH_CACHE_DIR="${CACHE_DIR}"
export ORCH_REPO_CACHE_DIR="${REPO_CACHE_DIR}"
export ORCH_MODEL_CACHE_DIR="${MODEL_CACHE_DIR}"
export ORCH_REMOTE_PREFECT_API_URL="${REMOTE_PREFECT_API_URL}"
export ORCH_REMOTE_MLFLOW_TRACKING_URI="${REMOTE_MLFLOW_TRACKING_URI}"
export PREFECT_UPSTREAM_URL="${PREFECT_UPSTREAM_BASE_URL}"
export MLFLOW_BACKEND_URL="${REMOTE_MLFLOW_TRACKING_URI}"
export WORKER_ROUTER_LOCAL_ONLY="${WORKER_ROUTER_LOCAL_ONLY:-true}"

mkdir -p "${CHECKPOINT_DIR}" "${CACHE_DIR}" "${REPO_CACHE_DIR}" "${MODEL_CACHE_DIR}"

/opt/venv/bin/uvicorn worker_router.main:app \
  --app-dir /app/src \
  --host 127.0.0.1 \
  --port "${WORKER_ROUTER_PORT}" &
WORKER_ROUTER_PID="$!"

/opt/venv/bin/python -m worker_artifacts.main &
WORKER_ARTIFACT_UPLOADER_PID="$!"

export PREFECT_API_URL="http://127.0.0.1:${WORKER_ROUTER_PORT}/prefect/api"
export MLFLOW_TRACKING_URI="http://127.0.0.1:${WORKER_ROUTER_PORT}/mlflow"
export STORAGE_API_URL="http://127.0.0.1:${WORKER_ROUTER_PORT}/artifact"

/opt/venv/bin/python -m common.prefect.work_queues \
  --pool "${POOL}" \
  --primary-queue "${PRIMARY_QUEUE}" \
  --batch-queue "${BATCH_QUEUE}"

set -- /opt/venv/bin/prefect worker start --pool "${POOL}" --type process --limit "${WORKER_LIMIT}"
OLD_IFS="${IFS}"
IFS=','
for queue in ${WORK_QUEUES}; do
  if [ -n "${queue}" ]; then
    set -- "$@" --work-queue "${queue}"
  fi
done
IFS="${OLD_IFS}"

log "startup summary: ${SUMMARY}"
log "worker router pid: ${WORKER_ROUTER_PID}"
log "artifact uploader pid: ${WORKER_ARTIFACT_UPLOADER_PID}"
log "local prefect api: ${PREFECT_API_URL}"
log "local mlflow uri: ${MLFLOW_TRACKING_URI}"
log "local storage api: ${STORAGE_API_URL}"
log "primary queue: ${PRIMARY_QUEUE}"
log "batch queue: ${BATCH_QUEUE}"
log "watched queues: ${WORK_QUEUES}"
log "launching: $*"

exec "$@"
