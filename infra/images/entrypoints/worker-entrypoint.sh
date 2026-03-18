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
QUEUE="${PREFECT_WORK_QUEUE:-}"
CHECKPOINT_DIR="${ORCHESTRATOR_CHECKPOINT_DIR:-/var/lib/orchestrator/checkpoints}"
REPO_CACHE_DIR="${ORCH_REPO_CACHE_DIR:-/var/lib/orchestrator/repo_cache}"
SUMMARY="$(
  /opt/venv/bin/python -m common.prefect.client_env summary --default-queue "gpu-fixed"
)"

mkdir -p "${CHECKPOINT_DIR}" "${REPO_CACHE_DIR}"

set -- /opt/venv/bin/prefect worker start --pool "${POOL}" --type process
if [ -n "${QUEUE}" ]; then
  set -- "$@" --work-queue "${QUEUE}"
fi

log "startup summary: ${SUMMARY}"
log "launching: $*"

exec "$@"
