#!/usr/bin/env bash

run_prefect_remote_action() {
  local action="$1"
  shift

  load_remote_env
  case "${action}" in
    up) remote_prefect_compose up -d --build "$@" ;;
    down) remote_prefect_compose down "$@" ;;
    ps) remote_prefect_compose ps "$@" ;;
    logs) remote_prefect_compose logs --tail=120 "$@" ;;
    build) remote_prefect_compose build "$@" ;;
    install) remote_project_exec "${PREFECT_VM_BOOTSTRAP_SCRIPT}" ;;
    *)
      echo "unknown remote prefect action: ${action}" >&2
      return 2
      ;;
  esac
}
