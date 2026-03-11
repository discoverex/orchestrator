#!/usr/bin/env bash

run_prefect_maintenance() {
  local action="$1"
  shift

  case "${action}" in
    flush) prefect_maintenance_command "${PREFECT_FLUSH_SCRIPT}" --once "$@" ;;
    prune) prefect_maintenance_command "${PREFECT_PRUNE_SCRIPT}" --apply "$@" ;;
    *)
      echo "unknown prefect maintenance action: ${action}" >&2
      return 2
      ;;
  esac
}
