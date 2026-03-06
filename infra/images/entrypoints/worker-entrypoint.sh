#!/usr/bin/env sh
set -eu

POOL="${PREFECT_WORK_POOL:-colab-gpu}"
QUEUE="${PREFECT_WORK_QUEUE:-}"

set -- /opt/venv/bin/prefect worker start --pool "${POOL}" --type process
if [ -n "${QUEUE}" ]; then
  set -- "$@" --work-queue "${QUEUE}"
fi

exec "$@"
