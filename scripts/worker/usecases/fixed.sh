#!/usr/bin/env bash

run_worker_fixed_action() {
  local action="$1"
  shift

  case "${action}" in
    up)
      ensure_executable "${GPU_INSTALL_SCRIPT}"
      "${GPU_INSTALL_SCRIPT}"
      export WORKER_RUNTIME_DIR="${RUNTIME_ROOT}/worker"
      export WORKER_CHECKPOINT_DIR="${RUNTIME_ROOT}/worker/checkpoints"
      export WORKER_REPO_CACHE_DIR="${RUNTIME_ROOT}/worker/repo_cache"
      # Ensure worker-managed runtime root exists before the container starts.
      runtime_init_target worker
      mkdir -p \
        "${RUNTIME_ROOT}/worker/model_cache" \
        "${RUNTIME_ROOT}/worker/checkpoints" \
        "${RUNTIME_ROOT}/worker/repo_cache"
      if [[ "$(id -u)" != "0" ]]; then
        echo "ERROR: worker runtime ownership must be prepared with elevated privileges." >&2
        echo "Run: sudo ./bin/cli worker fixed up" >&2
        return 1
      fi
      chown -R 10001:10001 "${RUNTIME_ROOT}/worker"
      chmod 0777 \
        "${RUNTIME_ROOT}/worker" \
        "${RUNTIME_ROOT}/worker/model_cache" \
        "${RUNTIME_ROOT}/worker/checkpoints" \
        "${RUNTIME_ROOT}/worker/repo_cache"
      compose_worker_fixed up -d --build "$@"
      ;;
    down) compose_worker_fixed down "$@" ;;
    ps) compose_worker_fixed ps "$@" ;;
    logs) compose_worker_fixed logs --tail=120 "$@" ;;
    build)
      compose_worker_fixed build worker "$@"
      ;;
    *)
      echo "unknown worker fixed action: ${action}" >&2
      return 2
      ;;
  esac
}
