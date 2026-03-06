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

run_storage() {
  compose_with_optional_env "${STORAGE_ENV}" "${STORAGE_COMPOSE}" "$@"
}

run_local() {
  compose_with_optional_env "" "${LOCAL_COMPOSE}" "$@"
}

run_register() {
  compose_with_optional_env "${REGISTER_ENV}" "${REGISTER_COMPOSE}" "$@"
}

run_prefect() {
  compose_with_optional_env "${PREFECT_ENV}" "${PREFECT_COMPOSE}" "$@"
}

run_worker_fixed() {
  compose_with_optional_env "${WORKER_FIXED_ENV}" "${WORKER_FIXED_COMPOSE}" "$@"
}

build_base_runtime() {
  docker build -f "${ROOT_DIR}/infra/images/base.Dockerfile" -t orchestrator-base:local "$@" "${ROOT_DIR}"
}

runtime_init_target() {
  local target="${1:-all}"
  case "${target}" in
    storage)
      mkdir -p "${RUNTIME_ROOT}/storage/data/minio" \
        "${RUNTIME_ROOT}/storage/data/mlflow-db" \
        "${RUNTIME_ROOT}/storage/backup" \
        "${RUNTIME_ROOT}/storage/logs"
      echo "runtime storage initialized: ${RUNTIME_ROOT}/storage"
      ;;
    worker)
      mkdir -p "${RUNTIME_ROOT}/worker/checkpoints" \
        "${RUNTIME_ROOT}/worker/logs"
      echo "runtime worker initialized: ${RUNTIME_ROOT}/worker"
      ;;
    all)
      runtime_init_target storage
      runtime_init_target worker
      ;;
    *)
      return 1
      ;;
  esac
}

require_executable() {
  local path="$1"
  if [[ ! -x "${path}" ]]; then
    echo "missing executable: ${path}" >&2
    return 1
  fi
}

has_prune_mode_arg() {
  local arg
  for arg in "$@"; do
    if [[ "${arg}" == "--prune-mode" || "${arg}" == --prune-mode=* ]]; then
      return 0
    fi
  done
  return 1
}

ensure_worker_gpu_runtime() {
  local script="${ROOT_DIR}/scripts/ops/install_nvidia_container_toolkit.sh"
  if [[ ! -x "${script}" ]]; then
    chmod +x "${script}"
  fi
  "${script}"
}
