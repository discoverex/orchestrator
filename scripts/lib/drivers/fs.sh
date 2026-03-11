#!/usr/bin/env bash

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

ensure_executable() {
  local path="$1"
  if [[ ! -x "${path}" ]]; then
    chmod +x "${path}"
  fi
}
