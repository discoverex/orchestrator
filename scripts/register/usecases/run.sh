#!/usr/bin/env bash

run_register_action() {
  local action="$1"
  shift

  case "${action}" in
    apply)
      uv run python "${ROOT_DIR}/scripts/register/prefect_apply.py" "$@"
      ;;
    *)
      echo "unknown register action: ${action}" >&2
      return 2
      ;;
  esac
}
