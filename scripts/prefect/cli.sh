#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/lib/bootstrap.sh"
source "${ROOT_DIR}/scripts/prefect/drivers/maintenance.sh"
source "${ROOT_DIR}/scripts/prefect/usecases/local.sh"
source "${ROOT_DIR}/scripts/prefect/usecases/remote.sh"
source "${ROOT_DIR}/scripts/prefect/usecases/maintenance.sh"
source "${ROOT_DIR}/scripts/prefect/usecases/workers.sh"

usage() {
  cat <<'EOF'
Usage:
  cli prefect <up|down|ps|logs|build|flush|prune|install|workers> [--remote] [args...]

Examples:
  cli prefect up
  cli prefect ps --remote
  cli prefect install --remote
  cli prefect workers --remote
EOF
}

parse_prefect_args() {
  PREFECT_REMOTE_REQUESTED=0
  PREFECT_PASSTHROUGH_ARGS=()
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --remote)
        PREFECT_REMOTE_REQUESTED=1
        ;;
      *)
        PREFECT_PASSTHROUGH_ARGS+=("$1")
        ;;
    esac
    shift
  done
}

action="${1:-help}"
shift || true
parse_prefect_args "$@"
set -- "${PREFECT_PASSTHROUGH_ARGS[@]}"

case "${action}" in
  help|-h|--help)
    usage
    ;;
  up|down|ps|logs|build)
    if [[ "${PREFECT_REMOTE_REQUESTED}" -eq 1 ]]; then
      run_prefect_remote_action "${action}" "$@"
    else
      run_prefect_local_action "${action}" "$@"
    fi
    ;;
  flush|prune)
    run_prefect_maintenance "${action}" "$@"
    ;;
  install)
    if [[ "${PREFECT_REMOTE_REQUESTED}" -ne 1 ]]; then
      echo "prefect install requires --remote" >&2
      exit 2
    fi
    run_prefect_remote_action "${action}" "$@"
    ;;
  workers)
    if [[ "${PREFECT_REMOTE_REQUESTED}" -ne 1 ]]; then
      echo "prefect workers requires --remote" >&2
      exit 2
    fi
    run_prefect_workers "$@"
    ;;
  *)
    echo "unknown prefect action: ${action}" >&2
    usage >&2
    exit 2
    ;;
esac
