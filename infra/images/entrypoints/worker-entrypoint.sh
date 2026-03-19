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
CHECKPOINT_DIR="${ORCHESTRATOR_CHECKPOINT_DIR:-/var/lib/orchestrator/checkpoints}"
REPO_CACHE_DIR="${ORCH_REPO_CACHE_DIR:-/var/lib/orchestrator/repo_cache}"
SUMMARY="$(
  /opt/venv/bin/python -m common.prefect.client_env summary --default-queue "gpu-fixed"
)"

mkdir -p "${CHECKPOINT_DIR}" "${REPO_CACHE_DIR}"

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
log "primary queue: ${PRIMARY_QUEUE}"
log "batch queue: ${BATCH_QUEUE}"
log "watched queues: ${WORK_QUEUES}"
log "launching: $*"

exec "$@"
