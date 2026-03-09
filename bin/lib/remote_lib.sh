#!/usr/bin/env bash

load_remote_env() {
  local root_dir="$1"
  if [[ -f "${root_dir}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${root_dir}/.env"
    set +a
  fi
}

normalize_deploy_key_path() {
  local key_path="$1"
  if [[ -n "${key_path}" && "${key_path}" == "~/"* ]]; then
    printf "%s/%s" "${HOME}" "${key_path#~/}"
    return
  fi
  printf "%s" "${key_path}"
}

ensure_remote_project_path() {
  local current_path="$1"
  local remote_user="$2"
  if [[ -n "${current_path}" ]]; then
    printf "%s" "${current_path}"
    return
  fi
  if [[ -n "${remote_user}" ]]; then
    printf "/home/%s/discoverex/orchestrator" "${remote_user}"
    return
  fi
  printf ""
}

require_remote_env() {
  : "${REMOTE_USERNAME:?REMOTE_USERNAME is required}"
  : "${REMOTE_HOST:?REMOTE_HOST is required}"
  : "${GITHUB_DEPLOY_KEY_PATH:?GITHUB_DEPLOY_KEY_PATH is required}"
}

remote_exec() {
  require_remote_env
  ssh -i "${GITHUB_DEPLOY_KEY_PATH}" "${REMOTE_USERNAME}@${REMOTE_HOST}" "$@"
}

remote_project_exec() {
  local cmd="$1"
  : "${REMOTE_PROJECT_PATH:?REMOTE_PROJECT_PATH is required}"
  local qpath
  qpath="${REMOTE_PROJECT_PATH//\'/\'\\\'\'}"
  remote_exec "cd '${qpath}' && ${cmd}"
}

remote_prefect_exec() {
  local cmd="$1"
  : "${REMOTE_PREFECT_PATH:?REMOTE_PREFECT_PATH is required}"
  local qpath
  qpath="${REMOTE_PREFECT_PATH//\'/\'\\\'\'}"
  remote_exec "cd '${qpath}' && ${cmd}"
}

join_quoted() {
  local out=""
  local arg
  for arg in "$@"; do
    out+=" $(printf "%q" "${arg}")"
  done
  printf "%s" "${out}"
}

remote_prefect_worker_ls() {
  remote_prefect_exec "if [[ -n \"\${REMOTE_PREFECT_ENV:-}\" && -f \"\${REMOTE_PREFECT_ENV}\" ]]; then set -a; source \"\${REMOTE_PREFECT_ENV}\"; set +a; elif [[ -f .env ]]; then set -a; source .env; set +a; fi; pools=\"\${REMOTE_WORKER_POOLS:-gpu-pool,colab-gpu}\"; IFS=',' read -r -a arr <<< \"\$pools\"; for p in \"\${arr[@]}\"; do echo \"== \$p ==\"; curl -fsS -H 'Content-Type: application/json' -d '{\"limit\":100,\"offset\":0}' \"http://127.0.0.1:\${PREFECT_BIND_PORT:-14200}/api/work_pools/\$p/workers/filter\" || true; echo; echo; done"
}
