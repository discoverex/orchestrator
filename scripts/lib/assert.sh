#!/usr/bin/env bash

require_executable() {
  local path="$1"
  if [[ ! -x "${path}" ]]; then
    echo "missing executable: ${path}" >&2
    return 1
  fi
}
