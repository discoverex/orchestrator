#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/lib/bootstrap.sh"
source "${ROOT_DIR}/scripts/observability/usecases/fixed_dummy_smoke.sh"
source "${ROOT_DIR}/scripts/observability/usecases/workers.sh"

usage() {
  cat <<'EOF'
Usage:
  cli observability <workers|fixed-dummy-smoke> [args...]
EOF
}

action="${1:-help}"
shift || true

case "${action}" in
  help|-h|--help)
    usage
    ;;
  workers)
    run_observability_workers "$@"
    ;;
  fixed-dummy-smoke)
    run_observability_fixed_dummy_smoke "$@"
    ;;
  *)
    echo "unknown observability action: ${action}" >&2
    usage >&2
    exit 2
    ;;
esac
