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

: "${CF_TUNNEL_ID:?CF_TUNNEL_ID is required}"
: "${CF_CREDENTIALS_FILE:?CF_CREDENTIALS_FILE is required}"
: "${PREFECT_HOSTNAME:?PREFECT_HOSTNAME is required}"
: "${PREFECT_API_DATABASE_CONNECTION_URL:?PREFECT_API_DATABASE_CONNECTION_URL is required}"

if [[ ! -f "${STACK_DIR}/.cloudflared/${CF_CREDENTIALS_FILE}" ]]; then
  echo "missing cloudflared credentials file: ${STACK_DIR}/.cloudflared/${CF_CREDENTIALS_FILE}" >&2
  exit 1
fi

pushd "${ROOT_DIR}" >/dev/null

docker compose --env-file "${STACK_ENV}" -f "${STACK_COMPOSE}" up -d --build

docker compose --env-file "${STACK_ENV}" -f "${STACK_COMPOSE}" ps

echo "prefect VM bootstrap complete"
echo "prefect api url: ${PREFECT_API_PUBLIC_URL:-https://${PREFECT_HOSTNAME}/api}"

popd >/dev/null
