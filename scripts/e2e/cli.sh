#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/lib/bootstrap.sh"
source "${ROOT_DIR}/scripts/e2e/usecases/local.sh"
source "${ROOT_DIR}/scripts/e2e/usecases/remote.sh"

usage() {
  cat <<'EOF'
Usage:
  cli e2e local [core|mlflow] [--keep-on-fail] [--timeout-sec N]
  cli e2e remote [engine] [--prefect-api-url URL] [--work-pool NAME] [--work-queue NAME] [--prune-mode dry-run|apply] [--bootstrap-worker] [--timeout-sec N]
  cli e2e remote dummy [--prefect-api-url URL] [--work-pool NAME] [--work-queue NAME] [--prune-mode dry-run|apply] [--bootstrap-worker] [--timeout-sec N]
EOF
}

action="${1:-help}"
shift || true

case "${action}" in
  help|-h|--help)
    usage
    ;;
  local)
    run_e2e_local "$@"
    ;;
  remote)
    run_e2e_remote "$@"
    ;;
  *)
    echo "unknown e2e action: ${action}" >&2
    usage >&2
    exit 2
    ;;
esac
