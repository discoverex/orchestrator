#!/usr/bin/env bash

run_storage_stack() {
  local action="$1"
  shift

  case "${action}" in
    up) compose_storage up -d --build "$@" ;;
    down) compose_storage down "$@" ;;
    ps) compose_storage ps "$@" ;;
    logs) compose_storage logs --tail=120 "$@" ;;
    build)
      build_base_runtime
      compose_storage build base-runtime worker-router mlflow "$@"
      ;;
    *)
      echo "unknown storage action: ${action}" >&2
      return 2
      ;;
  esac
}
