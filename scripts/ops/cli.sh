#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/lib/bootstrap.sh"
source "${ROOT_DIR}/scripts/ops/usecases/connect.sh"
source "${ROOT_DIR}/scripts/ops/usecases/postgres.sh"
source "${ROOT_DIR}/scripts/ops/usecases/dump.sh"
source "${ROOT_DIR}/scripts/ops/usecases/ci.sh"

usage() {
  cat <<'EOF'
Usage:
  cli ops <connect|postgres|dump|ci> [args...]
EOF
}

action="${1:-help}"
shift || true

case "${action}" in
  help|-h|--help)
    usage
    ;;
  connect)
    run_ops_connect "$@"
    ;;
  postgres)
    run_ops_postgres "$@"
    ;;
  dump)
    run_ops_dump "$@"
    ;;
  ci)
    run_ops_ci "$@"
    ;;
  *)
    echo "unknown ops action: ${action}" >&2
    usage >&2
    exit 2
    ;;
esac
