#!/usr/bin/env bash
set -euo pipefail

: "${PREFECT_API_URL:?PREFECT_API_URL is required}"

DEPLOYMENT_NAME="${REGISTER_DEPLOYMENT_NAME:-engine-run}"
WORK_POOL="${PREFECT_WORK_POOL:-gpu-pool}"
WORK_QUEUE="${PREFECT_WORK_QUEUE:-default}"
FIXED_DEPLOYMENT_NAME="${REGISTER_FIXED_DEPLOYMENT_NAME:-engine-run}"
FIXED_DEPLOYMENT_QUEUE="${REGISTER_FIXED_DEPLOYMENT_QUEUE:-gpu-fixed}"
COLAB_DEPLOYMENT_NAME="${REGISTER_COLAB_DEPLOYMENT_NAME:-engine-run-colab}"
COLAB_DEPLOYMENT_QUEUE="${REGISTER_COLAB_DEPLOYMENT_QUEUE:-gpu-colab}"
REGISTER_MODE="${REGISTER_DEPLOYMENT_MODE:-dual}"
DEPLOYMENT_VERSION="${REGISTER_DEPLOYMENT_VERSION:-}"

export PYTHONPATH=src

args=(python -m deployments.register --pool "$WORK_POOL")
if [[ "${REGISTER_MODE}" == "single" ]]; then
  args+=(--single-name "$DEPLOYMENT_NAME" --single-queue "$WORK_QUEUE")
else
  args+=(
    --fixed-name "$FIXED_DEPLOYMENT_NAME"
    --fixed-queue "$FIXED_DEPLOYMENT_QUEUE"
    --colab-name "$COLAB_DEPLOYMENT_NAME"
    --colab-queue "$COLAB_DEPLOYMENT_QUEUE"
  )
fi

if [[ -n "$DEPLOYMENT_VERSION" ]]; then
  args+=(--version "$DEPLOYMENT_VERSION")
fi

exec "${args[@]}"
