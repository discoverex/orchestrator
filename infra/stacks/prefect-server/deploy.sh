#!/usr/bin/env bash
set -euo pipefail

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "missing required env: ${name}" >&2
    exit 1
  fi
}

require_env REMOTE_DEPLOY_PATH
require_env PREFECT_SERVER_IMAGE
require_env PREFECT_API_PUBLIC_URL
require_env PREFECT_DB_PASSWORD
require_env FLUSH_TARGET_URL
require_env FLUSH_GATEWAY_TOKEN

: "${PREFECT_PORT:=4200}"
: "${PREFECT_BIND_PORT:=14200}"
: "${PREFECT_BIND_ADDRESS:=127.0.0.1}"
: "${PREFECT_DB_NAME:=prefect}"
: "${PREFECT_DB_USER:=prefect_user}"
: "${PREFECT_DB_DATA_DIR:=/srv/orchestrator/prefect-db}"
: "${PREFECT_MAINT_DATA_DIR:=/srv/orchestrator/prefect-maint}"
: "${FLUSH_INTERVAL_SEC:=600}"
: "${PRUNE_INTERVAL_SEC:=43200}"
: "${PRUNE_TTL_HOURS:=72}"
: "${FLUSH_PAGE_SIZE:=100}"
: "${FLUSH_MAX_RUNS:=500}"
: "${PRUNE_PAGE_SIZE:=200}"
: "${PRUNE_MAX_RUNS:=1000}"

export PREFECT_SERVER_IMAGE
export PREFECT_PORT
export PREFECT_BIND_PORT
export PREFECT_BIND_ADDRESS
export PREFECT_API_PUBLIC_URL
export PREFECT_DB_NAME
export PREFECT_DB_USER
export PREFECT_DB_PASSWORD
export PREFECT_DB_DATA_DIR
export FLUSH_TARGET_URL
export FLUSH_GATEWAY_TOKEN
export PREFECT_MAINT_DATA_DIR
export FLUSH_INTERVAL_SEC
export PRUNE_INTERVAL_SEC
export PRUNE_TTL_HOURS
export FLUSH_PAGE_SIZE
export FLUSH_MAX_RUNS
export PRUNE_PAGE_SIZE
export PRUNE_MAX_RUNS

# Optional Cloudflare Access headers for flush target.
if [[ -n "${FLUSH_CF_ACCESS_CLIENT_ID:-}" ]]; then
  export FLUSH_CF_ACCESS_CLIENT_ID
fi
if [[ -n "${FLUSH_CF_ACCESS_CLIENT_SECRET:-}" ]]; then
  export FLUSH_CF_ACCESS_CLIENT_SECRET
fi

mkdir -p "${REMOTE_DEPLOY_PATH}"
cd "${REMOTE_DEPLOY_PATH}"

if [[ -n "${GHCR_TOKEN:-}" ]]; then
  require_env GHCR_USERNAME
  export DOCKER_CONFIG
  DOCKER_CONFIG="$(mktemp -d)"
  trap 'rm -rf "${DOCKER_CONFIG}"' EXIT
  echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USERNAME}" --password-stdin
fi

docker compose pull
docker compose up -d prefect-db prefect-server prefect-maintenance
docker compose ps
