#!/usr/bin/env bash

run_local_stack() {
  local action="$1"
  shift

  case "${action}" in
    up) compose_local up -d --build "$@" ;;
    down) compose_local down "$@" ;;
    ps) compose_local ps "$@" ;;
    logs) compose_local logs --tail=120 "$@" ;;
    build)
      build_base_runtime
      compose_local build base-runtime worker-router worker "$@"
      ;;
    *)
      echo "unknown local action: ${action}" >&2
      return 2
      ;;
  esac
}
