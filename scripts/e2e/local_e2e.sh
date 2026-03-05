#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
exec ./scripts/e2e/e2e_orchestrator.sh --mode core "$@"
