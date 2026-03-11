#!/usr/bin/env bash

run_worker_fixed_action() {
  local action="$1"
  shift

  case "${action}" in
    up)
      ensure_executable "${GPU_INSTALL_SCRIPT}"
      "${GPU_INSTALL_SCRIPT}"
      compose_worker_fixed up -d --build "$@"
      ;;
    down) compose_worker_fixed down "$@" ;;
    ps) compose_worker_fixed ps "$@" ;;
    logs) compose_worker_fixed logs --tail=120 "$@" ;;
    build)
      build_base_runtime
      compose_worker_fixed build base-runtime worker "$@"
      ;;
    *)
      echo "unknown worker fixed action: ${action}" >&2
      return 2
      ;;
  esac
}
