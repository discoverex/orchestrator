#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/lib/bootstrap.sh"
source "${ROOT_DIR}/scripts/base/usecases/build.sh"

usage() {
  cat <<'EOF'
Usage:
  cli base build [docker build args...]
EOF
}

action="${1:-help}"
shift || true

case "${action}" in
  help|-h|--help)
    usage
    ;;
  build)
    run_base_build "$@"
    ;;
  *)
    echo "unknown base action: ${action}" >&2
    usage >&2
    exit 2
    ;;
esac
