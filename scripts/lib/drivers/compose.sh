#!/usr/bin/env bash

compose_with_optional_env() {
  local env_file="$1"
  shift
  local compose_file="$1"
  shift

  if [[ -n "${env_file}" ]]; then
    docker compose --env-file "${env_file}" -f "${compose_file}" "$@"
    return
  fi

  docker compose -f "${compose_file}" "$@"
}

compose_storage() {
  compose_with_optional_env "${STORAGE_ENV}" "${STORAGE_COMPOSE}" "$@"
}

compose_local() {
  compose_with_optional_env "" "${LOCAL_COMPOSE}" "$@"
}

compose_register() {
  compose_with_optional_env "${REGISTER_ENV}" "${REGISTER_COMPOSE}" "$@"
}

compose_prefect() {
  compose_with_optional_env "${PREFECT_ENV}" "${PREFECT_COMPOSE}" "$@"
}

compose_worker_fixed() {
  compose_with_optional_env "${WORKER_FIXED_ENV}" "${WORKER_FIXED_COMPOSE}" "$@"
}

build_base_runtime() {
  docker build -f "${BASE_BUILD_DOCKERFILE}" -t orchestrator-base:local "$@" "${ROOT_DIR}"
}

build_prefect_runtime() {
  docker build -f "${PREFECT_BUILD_DOCKERFILE}" -t orchestrator-prefect-server:local "$@" "${ROOT_DIR}"
}
