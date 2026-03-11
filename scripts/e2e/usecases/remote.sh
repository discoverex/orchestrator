#!/usr/bin/env bash

DUMMY_JOB_SPEC_FILE="${ROOT_DIR}/scripts/e2e/fixed_dummy_inline_job.json"

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

_exec_e2e_remote_script() {
  local mode="$1"
  shift
  require_executable "${ROOT_DIR}/scripts/e2e/e2e_remote_prefect_storage.sh"

  if ! e2e_remote_has_arg "--prefect-api-url" "$@"; then
    load_repo_env
    if [[ -n "${PREFECT_API_URL:-}" ]]; then
      set -- --prefect-api-url "${PREFECT_API_URL}" "$@"
    fi
  fi

  if [[ "${mode}" == "dummy" ]]; then
    if [[ ! -f "${DUMMY_JOB_SPEC_FILE}" ]]; then
      echo "missing dummy job spec file: ${DUMMY_JOB_SPEC_FILE}" >&2
      return 1
    fi
    set -- --mode dummy --job-spec-file "${DUMMY_JOB_SPEC_FILE}" "$@"
  else
    set -- --mode engine "$@"
  fi

  if ! e2e_remote_has_arg "--prune-mode" "$@"; then
    exec "${ROOT_DIR}/scripts/e2e/e2e_remote_prefect_storage.sh" --prune-mode dry-run "$@"
  fi

  exec "${ROOT_DIR}/scripts/e2e/e2e_remote_prefect_storage.sh" "$@"
}

run_e2e_remote() {
  local mode="engine"
  if [[ $# -gt 0 && "${1}" != --* ]]; then
    mode="$1"
    shift
  fi

  case "${mode}" in
    engine|dummy)
      _exec_e2e_remote_script "${mode}" "$@"
      ;;
    *)
      echo "unknown remote e2e mode: ${mode}" >&2
      return 2
      ;;
  esac
}
