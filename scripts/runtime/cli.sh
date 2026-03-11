#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/lib/bootstrap.sh"
source "${ROOT_DIR}/scripts/runtime/usecases/init.sh"

usage() {
  cat <<'EOF'
Usage:
  cli runtime init [storage|worker|all]
EOF
}

action="${1:-help}"
shift || true

case "${action}" in
  help|-h|--help)
    usage
    ;;
  init)
    if ! run_runtime_init "${1:-all}"; then
      echo "unknown runtime init target: ${1:-all}" >&2
      usage >&2
      exit 2
    fi
    ;;
  *)
    echo "unknown runtime action: ${action}" >&2
    usage >&2
    exit 2
    ;;
esac
