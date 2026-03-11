#!/usr/bin/env bash

run_python_tool() {
  local script_path="$1"
  shift
  require_executable "${script_path}"
  exec python3 "${script_path}" "$@"
}
