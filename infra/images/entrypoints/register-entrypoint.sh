#!/usr/bin/env bash
set -euo pipefail

: "${PREFECT_API_URL:?PREFECT_API_URL is required}"

if [[ "${PREFECT_CLIENT_CUSTOM_HEADERS:-}" == "" ]]; then
  unset PREFECT_CLIENT_CUSTOM_HEADERS || true
fi

eval "$(
  /opt/venv/bin/python -c \
  'from common.prefect.client_env import shell_exports; print(shell_exports())'
)"

DEPLOYMENT_NAME="${REGISTER_DEPLOYMENT_NAME:-e2e-test}"
WORK_POOL="${PREFECT_WORK_POOL:-gpu-pool}"
WORK_QUEUE="${PREFECT_WORK_QUEUE:-default}"
FIXED_DEPLOYMENT_NAME="${REGISTER_FIXED_DEPLOYMENT_NAME:-e2e-test}"
FIXED_DEPLOYMENT_QUEUE="${REGISTER_FIXED_DEPLOYMENT_QUEUE:-gpu-fixed}"
COLAB_DEPLOYMENT_NAME="${REGISTER_COLAB_DEPLOYMENT_NAME:-e2e-test-colab}"
COLAB_DEPLOYMENT_QUEUE="${REGISTER_COLAB_DEPLOYMENT_QUEUE:-gpu-colab}"
COMPAT_FIXED_DEPLOYMENT_NAME="${REGISTER_COMPAT_FIXED_DEPLOYMENT_NAME:-e2e-test-legacy}"
COMPAT_FIXED_DEPLOYMENT_QUEUE="${REGISTER_COMPAT_FIXED_DEPLOYMENT_QUEUE:-gpu-fixed}"
COMPAT_COLAB_DEPLOYMENT_NAME="${REGISTER_COMPAT_COLAB_DEPLOYMENT_NAME:-e2e-test-colab-legacy}"
COMPAT_COLAB_DEPLOYMENT_QUEUE="${REGISTER_COMPAT_COLAB_DEPLOYMENT_QUEUE:-gpu-colab}"
REGISTER_MODE="${REGISTER_DEPLOYMENT_MODE:-dual}"
DEPLOYMENT_VERSION="${REGISTER_DEPLOYMENT_VERSION:-}"
REGISTER_COMPAT_ALIASES="${REGISTER_COMPAT_ALIASES:-false}"
FLOW_SOURCE="${REGISTER_FLOW_SOURCE:-/app}"
FLOW_ENTRYPOINT="${REGISTER_FLOW_ENTRYPOINT:-src/flows/engine_run/flow.py:run_job_flow}"

export PYTHONPATH=src

args=(
  python -m deployments.register
  --pool "$WORK_POOL"
  --flow-source "$FLOW_SOURCE"
  --flow-entrypoint "$FLOW_ENTRYPOINT"
)
if [[ "${REGISTER_MODE}" == "single" ]]; then
  args+=(--single-name "$DEPLOYMENT_NAME" --single-queue "$WORK_QUEUE")
else
  args+=(
    --fixed-name "$FIXED_DEPLOYMENT_NAME"
    --fixed-queue "$FIXED_DEPLOYMENT_QUEUE"
    --colab-name "$COLAB_DEPLOYMENT_NAME"
    --colab-queue "$COLAB_DEPLOYMENT_QUEUE"
    --compat-fixed-name "$COMPAT_FIXED_DEPLOYMENT_NAME"
    --compat-fixed-queue "$COMPAT_FIXED_DEPLOYMENT_QUEUE"
    --compat-colab-name "$COMPAT_COLAB_DEPLOYMENT_NAME"
    --compat-colab-queue "$COMPAT_COLAB_DEPLOYMENT_QUEUE"
  )
fi

if [[ "${REGISTER_COMPAT_ALIASES}" == "true" ]]; then
  args+=(--register-compat-aliases)
else
  args+=(--no-register-compat-aliases)
fi

if [[ -n "$DEPLOYMENT_VERSION" ]]; then
  args+=(--version "$DEPLOYMENT_VERSION")
fi

exec "${args[@]}"
