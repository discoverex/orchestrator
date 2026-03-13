#!/usr/bin/env bash

run_worker_fixed_action() {
  local action="$1"
  shift

  case "${action}" in
    up)
      ensure_executable "${GPU_INSTALL_SCRIPT}"
      "${GPU_INSTALL_SCRIPT}"
      # Ensure runtime directory exists and has correct permissions
      runtime_init_target worker
      if [[ -d "${RUNTIME_ROOT}/worker/checkpoints" ]]; then
        # Ensure it is writable by the appuser (UID 10001) in the container
        # Note: If running as root or with sudo, this will apply the UID.
        # If it fails, the user will be warned.
        sudo chown -R 10001:10001 "${RUNTIME_ROOT}/worker/checkpoints" || {
          echo "Warning: failed to chown ${RUNTIME_ROOT}/worker/checkpoints to UID 10001." >&2
          echo "If PermissionError occurs, run: sudo chown -R 10001:10001 ${RUNTIME_ROOT}/worker/checkpoints" >&2
        }
      fi
      compose_worker_fixed up -d --build "$@"
      ;;
    down) compose_worker_fixed down "$@" ;;
    ps) compose_worker_fixed ps "$@" ;;
    logs) compose_worker_fixed logs --tail=120 "$@" ;;
    build)
      build_base_runtime
      compose_worker_fixed build base-runtime worker "$@"
      ;;
    *)
      echo "unknown worker fixed action: ${action}" >&2
      return 2
      ;;
  esac
}
