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
  'from common.prefect_client_env import shell_exports; print(shell_exports(default_queue="gpu-fixed"))'
)"

POOL="${PREFECT_WORK_POOL:-gpu-pool}"
QUEUE="${PREFECT_WORK_QUEUE:-}"
SUMMARY="$(
  /opt/venv/bin/python -c \
  'from common.prefect_client_env import startup_summary; import json; print(json.dumps(startup_summary(default_queue="gpu-fixed").model_dump(mode="json"), ensure_ascii=True, sort_keys=True))'
)"

set -- /opt/venv/bin/prefect worker start --pool "${POOL}" --type process
if [ -n "${QUEUE}" ]; then
  set -- "$@" --work-queue "${QUEUE}"
fi

log "startup summary: ${SUMMARY}"
log "launching: $*"

exec "$@"
