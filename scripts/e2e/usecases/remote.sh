#!/usr/bin/env bash

e2e_remote_has_arg() {
  local needle="$1"
  shift
  local arg
  for arg in "$@"; do
    if [[ "${arg}" == "${needle}" || "${arg}" == "${needle}="* ]]; then
      return 0
    fi
  done
  return 1
}

run_e2e_remote() {
  require_executable "${ROOT_DIR}/scripts/e2e/e2e_remote_prefect_storage.sh"

  if ! e2e_remote_has_arg "--prefect-api-url" "$@"; then
    load_repo_env
    if [[ -n "${PREFECT_API_URL:-}" ]]; then
      set -- --prefect-api-url "${PREFECT_API_URL}" "$@"
    fi
  fi

  if ! e2e_remote_has_arg "--prune-mode" "$@"; then
    exec "${ROOT_DIR}/scripts/e2e/e2e_remote_prefect_storage.sh" --prune-mode dry-run "$@"
  fi

  exec "${ROOT_DIR}/scripts/e2e/e2e_remote_prefect_storage.sh" "$@"
}
