#!/usr/bin/env bash
set -euo pipefail

: "${PREFECT_API_URL:?PREFECT_API_URL is required}"

if [[ "${PREFECT_CLIENT_CUSTOM_HEADERS:-}" == "" ]]; then
  unset PREFECT_CLIENT_CUSTOM_HEADERS || true
fi

eval "$(
  uv run python -c \
  'from common.prefect.client_env import shell_exports; print(shell_exports())'
)"

DEPLOYMENT_NAME="${REGISTER_DEPLOYMENT_NAME:-e2e-test}"
WORK_POOL="${PREFECT_WORK_POOL:-gpu-pool}"
WORK_QUEUE="${PREFECT_WORK_QUEUE:-default}"
FIXED_DEPLOYMENT_NAME="${REGISTER_FIXED_DEPLOYMENT_NAME:-}"
FIXED_DEPLOYMENT_QUEUE="${REGISTER_FIXED_DEPLOYMENT_QUEUE:-}"
COLAB_DEPLOYMENT_NAME="${REGISTER_COLAB_DEPLOYMENT_NAME:-}"
COLAB_DEPLOYMENT_QUEUE="${REGISTER_COLAB_DEPLOYMENT_QUEUE:-}"
REGISTER_MODE="${REGISTER_DEPLOYMENT_MODE:-dual}"
DEPLOYMENT_VERSION="${REGISTER_DEPLOYMENT_VERSION:-}"
SPEC_FILE="${REGISTER_SPEC_FILE:-/app/deployments/e2e/e2e-deployments.yaml}"
FLOW_SOURCE="${REGISTER_FLOW_SOURCE:-/app}"
FLOW_ENTRYPOINT="${REGISTER_FLOW_ENTRYPOINT:-}"

export PYTHONPATH=src

args=(
  uv run python -m deployments.register
  --spec-file "$SPEC_FILE"
  --pool "$WORK_POOL"
  --flow-source "$FLOW_SOURCE"
)
if [[ -n "$FLOW_ENTRYPOINT" ]]; then
  args+=(--flow-entrypoint "$FLOW_ENTRYPOINT")
fi
if [[ "${REGISTER_MODE}" == "single" ]]; then
  args+=(--single-name "$DEPLOYMENT_NAME" --single-queue "$WORK_QUEUE")
else
  [[ -n "$FIXED_DEPLOYMENT_NAME" ]] && args+=(--fixed-name "$FIXED_DEPLOYMENT_NAME")
  [[ -n "$FIXED_DEPLOYMENT_QUEUE" ]] && args+=(--fixed-queue "$FIXED_DEPLOYMENT_QUEUE")
  [[ -n "$COLAB_DEPLOYMENT_NAME" ]] && args+=(--colab-name "$COLAB_DEPLOYMENT_NAME")
  [[ -n "$COLAB_DEPLOYMENT_QUEUE" ]] && args+=(--colab-queue "$COLAB_DEPLOYMENT_QUEUE")
fi

if [[ -n "$DEPLOYMENT_VERSION" ]]; then
  args+=(--version "$DEPLOYMENT_VERSION")
fi

exec "${args[@]}"
