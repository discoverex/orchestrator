#!/usr/bin/env bash
set -euo pipefail

: "${PREFECT_API_URL:?PREFECT_API_URL is required}"

DEPLOYMENT_NAME="${REGISTER_DEPLOYMENT_NAME:-engine-run}"
WORK_POOL="${PREFECT_WORK_POOL:-colab-gpu}"
WORK_QUEUE="${PREFECT_WORK_QUEUE:-default}"
DEPLOYMENT_VERSION="${REGISTER_DEPLOYMENT_VERSION:-}"

export PYTHONPATH=src

args=(python -m deployments.register --name "$DEPLOYMENT_NAME" --pool "$WORK_POOL" --queue "$WORK_QUEUE")
if [[ -n "$DEPLOYMENT_VERSION" ]]; then
  args+=(--version "$DEPLOYMENT_VERSION")
fi

exec "${args[@]}"
