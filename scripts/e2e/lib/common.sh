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
  local step_tmp_log
  step_tmp_log=$(mktemp)
  if "$@" >"${step_tmp_log}" 2>&1; then
    cat "${step_tmp_log}" >>"${run_log}"
    record_step_line "${steps_file}" "${name}" "pass" "ok"
    rm -f "${step_tmp_log}"
    return 0
  fi
  cat "${step_tmp_log}" >>"${run_log}"
  record_step_line "${steps_file}" "${name}" "fail" "failed (see run.log)"
  echo "FAILED: STEP ${name}" >&2
  echo "--- BEGIN STEP LOG: ${name} ---" >&2
  cat "${step_tmp_log}" >&2
  echo "--- END STEP LOG: ${name} ---" >&2
  rm -f "${step_tmp_log}"
  return 1
}

must_step_cmd() {
  local run_log="$1"
  local steps_file="$2"
  local fail_cb="$3"
  local name="$4"
  shift 4
  if run_step_cmd "${run_log}" "${steps_file}" "${name}" "$@"; then
    return 0
  fi
  if [[ -n "${fail_cb}" && "$(type -t "${fail_cb}")" == "function" ]]; then
    "${fail_cb}"
  fi
  exit 1
}
