#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

log() {
  printf '[nvidia-toolkit] %s\n' "$*"
}

die() {
  log "$*"
  exit 1
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    die "missing required command: $1"
  fi
}

is_runtime_configured() {
  if ! command -v docker >/dev/null 2>&1; then
    return 1
  fi

  docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'
}

verify_gpu_driver() {
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    log "nvidia-smi not found on host (driver not installed or PATH missing)"
    return 1
  fi

  nvidia-smi -L >/dev/null 2>&1
}

install_toolkit_debian_like() {
  if [[ ! -f /etc/os-release ]]; then
    die "/etc/os-release not found; unsupported OS"
  fi

  # shellcheck disable=SC1091
  source /etc/os-release

  local distribution="${ID}${VERSION_ID}"
  local keyring="/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg"
  local list_file="/etc/apt/sources.list.d/nvidia-container-toolkit.list"
  local tmp_keyring
  tmp_keyring="$(mktemp)"

  require_cmd apt-get
  require_cmd curl
  require_cmd sed
  require_cmd tee
  require_cmd mktemp

  log "installing prerequisites"
  ${SUDO} apt-get update
  ${SUDO} apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg

  require_cmd gpg

  log "installing NVIDIA Container Toolkit repo for ${distribution}"

  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor > "${tmp_keyring}"

  ${SUDO} install -D -m 0644 "${tmp_keyring}" "${keyring}"
  rm -f "${tmp_keyring}"

  curl -fsSL "https://nvidia.github.io/libnvidia-container/${distribution}/libnvidia-container.list" \
    | sed "s#^deb https://#deb [signed-by=${keyring}] https://#g" \
    | ${SUDO} tee "${list_file}" >/dev/null

  ${SUDO} apt-get update
  ${SUDO} apt-get install -y --no-install-recommends nvidia-container-toolkit
}

restart_docker() {
  if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
    ${SUDO} systemctl restart docker
    return
  fi

  if command -v service >/dev/null 2>&1; then
    ${SUDO} service docker restart
    return
  fi

  die "could not restart docker automatically"
}

configure_runtime() {
  require_cmd docker
  require_cmd nvidia-ctk

  log "configuring NVIDIA runtime for Docker"
  ${SUDO} nvidia-ctk runtime configure --runtime=docker

  log "restarting Docker"
  restart_docker
}

main() {
  require_cmd docker

  if is_runtime_configured && command -v nvidia-ctk >/dev/null 2>&1; then
    log "nvidia container runtime already configured"
  else
    if command -v apt-get >/dev/null 2>&1; then
      install_toolkit_debian_like
    else
      die "unsupported platform: automatic install requires apt-get"
    fi

    configure_runtime
  fi

  if verify_gpu_driver; then
    log "host driver detected via nvidia-smi"
    log "ready"
    exit 0
  fi

  log "toolkit installed/configured, but host GPU driver check failed"
  exit 1
}

main "$@"