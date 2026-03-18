#!/usr/bin/env bash

run_e2e_local() {
  require_executable "${ROOT_DIR}/scripts/e2e/e2e_local_orchestrator.sh"

  local mode="${1:-}"
  case "${mode}" in
    core|mlflow)
      shift
      exec "${ROOT_DIR}/scripts/e2e/e2e_local_orchestrator.sh" --mode "${mode}" "$@"
      ;;
    priority)
      shift
      exec "${ROOT_DIR}/scripts/e2e/e2e_local_prefect_priority.sh" "$@"
      ;;
    "")
      exec "${ROOT_DIR}/scripts/e2e/e2e_local_orchestrator.sh" --mode core "$@"
      ;;
    *)
      exec "${ROOT_DIR}/scripts/e2e/e2e_local_orchestrator.sh" "${mode}" "$@"
      ;;
  esac
}
