#!/usr/bin/env bash

run_worker_register_gpu() {
  uv run python "${ROOT_DIR}/scripts/register/prefect_apply.py" "$@"
}
