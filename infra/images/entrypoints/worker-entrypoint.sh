#!/usr/bin/env sh
set -eu

POOL="${PREFECT_WORK_POOL:-colab-gpu}"
exec /opt/venv/bin/prefect worker start --pool "${POOL}" --type process
