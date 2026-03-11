#!/usr/bin/env bash

run_register_action() {
  local action="$1"
  shift

  case "${action}" in
    run) compose_register run --rm register "$@" ;;
    build)
      build_base_runtime
      compose_register build base-runtime register "$@"
      ;;
    *)
      echo "unknown register action: ${action}" >&2
      return 2
      ;;
  esac
}
