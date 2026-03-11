#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/lib/bootstrap.sh"
source "${ROOT_DIR}/scripts/storage/usecases/stack.sh"

usage() {
  cat <<'EOF'
Usage:
  cli storage <up|down|ps|logs|build> [args...]
EOF
}

action="${1:-help}"
shift || true

case "${action}" in
  help|-h|--help)
    usage
    ;;
  up|down|ps|logs|build)
    run_storage_stack "${action}" "$@"
    ;;
  *)
    echo "unknown storage action: ${action}" >&2
    usage >&2
    exit 2
    ;;
esac
