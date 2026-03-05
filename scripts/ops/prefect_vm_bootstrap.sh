#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STACK_DIR="${ROOT_DIR}/infra/stacks/prefect-server"
STACK_ENV="${STACK_DIR}/.env"
STACK_COMPOSE="${STACK_DIR}/docker-compose.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin not found" >&2
  exit 1
fi

if [[ ! -f "${STACK_ENV}" ]]; then
  echo "missing env file: ${STACK_ENV}" >&2
  echo "copy from ${STACK_DIR}/.env.example and fill required values" >&2
  exit 1
fi

set -a
source "${STACK_ENV}"
set +a

: "${PREFECT_API_PUBLIC_URL:?PREFECT_API_PUBLIC_URL is required}"
: "${PREFECT_DB_NAME:?PREFECT_DB_NAME is required}"
: "${PREFECT_DB_USER:?PREFECT_DB_USER is required}"
: "${PREFECT_DB_PASSWORD:?PREFECT_DB_PASSWORD is required}"
: "${FLUSH_TARGET_URL:?FLUSH_TARGET_URL is required}"
: "${FLUSH_GATEWAY_TOKEN:?FLUSH_GATEWAY_TOKEN is required}"

pushd "${ROOT_DIR}" >/dev/null

docker compose --env-file "${STACK_ENV}" -f "${STACK_COMPOSE}" up -d

docker compose --env-file "${STACK_ENV}" -f "${STACK_COMPOSE}" ps

echo "prefect VM bootstrap complete"
echo "prefect api url: ${PREFECT_API_PUBLIC_URL}"

popd >/dev/null
