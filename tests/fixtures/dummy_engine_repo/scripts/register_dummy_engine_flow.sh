#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ENGINE_SOURCE="${ROOT_DIR}"

export PYTHONPATH="${ROOT_DIR}/src"

eval "$(
  uv run python -c \
  'from common.prefect.client_env import shell_exports; print(shell_exports())'
)"

exec uv run python -m deployments.register \
  --pool "${PREFECT_WORK_POOL:-gpu-pool}" \
  --flow-source "${ENGINE_SOURCE}" \
  --flow-entrypoint "tests/fixtures/dummy_engine_repo/src/dummy_engine/prefect_flow.py:dummy_engine_flow" \
  --fixed-name "${REGISTER_FIXED_DEPLOYMENT_NAME:-discoverex-engine-run}" \
  --fixed-queue "${REGISTER_FIXED_DEPLOYMENT_QUEUE:-gpu-fixed}" \
  --colab-name "${REGISTER_COLAB_DEPLOYMENT_NAME:-discoverex-engine-run-colab}" \
  --colab-queue "${REGISTER_COLAB_DEPLOYMENT_QUEUE:-gpu-colab}" \
  "${@}"
