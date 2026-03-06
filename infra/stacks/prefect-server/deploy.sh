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
ENV_FILE_NAME="${ENV_FILE_NAME:-.env.runtime}"
ENV_FILE_PATH="${REMOTE_DEPLOY_PATH}/${ENV_FILE_NAME}"

mkdir -p "${REMOTE_DEPLOY_PATH}"
cd "${REMOTE_DEPLOY_PATH}"

if [[ ! -f "${ENV_FILE_PATH}" ]]; then
  echo "missing env file: ${ENV_FILE_PATH}" >&2
  exit 1
fi

cleanup_env_file() {
  rm -f "${ENV_FILE_PATH}"
}

cleanup_all() {
  cleanup_env_file
  if [[ -n "${DOCKER_CONFIG:-}" ]]; then
    rm -rf "${DOCKER_CONFIG}"
  fi
}
trap cleanup_all EXIT

set -a
# shellcheck disable=SC1090
source "${ENV_FILE_PATH}"
set +a

require_env PREFECT_SERVER_IMAGE
require_env PREFECT_HOSTNAMES
require_env PREFECT_API_PUBLIC_URL
require_env PREFECT_DB_PASSWORD
require_env FLUSH_TARGET_URL
require_env FLUSH_GATEWAY_TOKEN

if [[ -n "${GHCR_TOKEN:-}" ]]; then
  require_env GHCR_USERNAME
  export DOCKER_CONFIG="$(mktemp -d)"
  echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USERNAME}" --password-stdin
fi

docker compose --env-file "${ENV_FILE_PATH}" pull
docker compose --env-file "${ENV_FILE_PATH}" up -d --wait prefect-db prefect-server prefect-maintenance caddy
docker compose --env-file "${ENV_FILE_PATH}" ps
