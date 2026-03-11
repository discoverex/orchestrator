#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/lib/bootstrap.sh"
source "${ROOT_DIR}/scripts/register/usecases/run.sh"

usage() {
  cat <<'EOF'
Usage:
  cli register <run|build> [args...]
EOF
}

action="${1:-help}"
shift || true

case "${action}" in
  help|-h|--help)
    usage
    ;;
  run|build)
    run_register_action "${action}" "$@"
    ;;
  *)
    echo "unknown register action: ${action}" >&2
    usage >&2
    exit 2
    ;;
esac
