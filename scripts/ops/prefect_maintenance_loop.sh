#!/usr/bin/env bash
set -euo pipefail

FLUSH_INTERVAL_SEC="${FLUSH_INTERVAL_SEC:-600}"
PRUNE_INTERVAL_SEC="${PRUNE_INTERVAL_SEC:-43200}"
PRUNE_TTL_HOURS="${PRUNE_TTL_HOURS:-72}"
PRUNE_STAMP="${PRUNE_STAMP:-/var/lib/orchestrator/prefect-flush/last_prune_epoch}"

mkdir -p "$(dirname "${PRUNE_STAMP}")"

if [[ ! -f "${PRUNE_STAMP}" ]]; then
  echo 0 > "${PRUNE_STAMP}"
fi

while true; do
  echo "[maint] flush started $(date -u +%FT%TZ)"
  PYTHONPATH=/opt/orchestrator/src:/opt/orchestrator python /opt/orchestrator/scripts/ops/prefect_flush_completed.py --once || echo "[maint] flush failed"

  now_epoch="$(date +%s)"
  last_prune_epoch="$(cat "${PRUNE_STAMP}" 2>/dev/null || echo 0)"
  elapsed="$((now_epoch - last_prune_epoch))"
  if (( elapsed >= PRUNE_INTERVAL_SEC )); then
    echo "[maint] prune started $(date -u +%FT%TZ) ttl_hours=${PRUNE_TTL_HOURS}"
    PYTHONPATH=/opt/orchestrator/src:/opt/orchestrator python /opt/orchestrator/scripts/ops/prefect_prune_completed.py --apply --ttl-hours "${PRUNE_TTL_HOURS}" || echo "[maint] prune failed"
    echo "${now_epoch}" > "${PRUNE_STAMP}"
  fi

  sleep "${FLUSH_INTERVAL_SEC}"
done
