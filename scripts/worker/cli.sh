#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/lib/bootstrap.sh"
source "${ROOT_DIR}/scripts/worker/usecases/fixed.sh"
source "${ROOT_DIR}/scripts/worker/usecases/submit.sh"

usage() {
  cat <<'EOF'
Usage:
  cli worker fixed <up|down|ps|logs|build> [args...]
  cli worker submit [router args...]
EOF
}

action="${1:-help}"
shift || true

case "${action}" in
  help|-h|--help)
    usage
    ;;
  fixed)
    subaction="${1:-}"
    shift || true
    case "${subaction}" in
      up|down|ps|logs|build)
        run_worker_fixed_action "${subaction}" "$@"
        ;;
      *)
        echo "unknown worker fixed action: ${subaction}" >&2
        usage >&2
        exit 2
        ;;
    esac
    ;;
  submit)
    run_worker_submit "$@"
    ;;
  *)
    echo "unknown worker action: ${action}" >&2
    usage >&2
    exit 2
    ;;
esac
