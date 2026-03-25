#!/usr/bin/env bash

prefect_maintenance_command() {
  local script_path="$1"
  shift

  if [[ "${PREFECT_REMOTE_REQUESTED:-0}" -eq 1 ]]; then
    load_remote_env
    remote_prefect_compose run --rm prefect-maintenance python "${script_path}" "$@"
    return
  fi

  compose_prefect run --rm prefect-maintenance python "${script_path}" "$@"
}
