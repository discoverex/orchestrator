#!/usr/bin/env bash

run_prefect_local_action() {
  local action="$1"
  shift

  case "${action}" in
    up) compose_prefect up -d "$@" ;;
    down) compose_prefect down "$@" ;;
    ps) compose_prefect ps "$@" ;;
    logs) compose_prefect logs --tail=120 "$@" ;;
    build)
      build_base_runtime
      build_prefect_runtime "$@"
      ;;
    *)
      echo "unknown prefect action: ${action}" >&2
      return 2
      ;;
  esac
}
