#!/usr/bin/env bash

run_python_tool() {
  local script_path="$1"
  shift
  require_executable "${script_path}"
  PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}:${PYTHONPATH:-}" \
    exec uv run python "${script_path}" "$@"
}
