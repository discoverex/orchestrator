#!/usr/bin/env bash

load_env_file_if_exists() {
  local env_path="$1"
  if [[ "${E2E_SKIP_DOTENV:-false}" == "true" && "$(basename "${env_path}")" == ".env" ]]; then
    return 0
  fi
  if [[ -f "${env_path}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_path}"
    set +a
  fi
}

log_step_line() {
  local run_log="$1"
  shift
  echo "[$(date +%H:%M:%S)] $*" | tee -a "${run_log}"
}

record_step_line() {
  local steps_file="$1"
  local name="$2"
  local status="$3"
  local message="$4"
  printf "%s\t%s\t%s\n" "${name}" "${status}" "${message}" >> "${steps_file}"
}

run_step_cmd() {
  local run_log="$1"
  local steps_file="$2"
  local name="$3"
  shift 3
  log_step_line "${run_log}" "STEP ${name}"
  if "$@" >>"${run_log}" 2>&1; then
    record_step_line "${steps_file}" "${name}" "pass" "ok"
    return 0
  fi
  record_step_line "${steps_file}" "${name}" "fail" "failed (see run.log)"
  return 1
}
