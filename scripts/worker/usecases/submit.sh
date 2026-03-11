#!/usr/bin/env bash

run_worker_submit() {
  run_python_tool "${SUBMIT_ROUTER_SCRIPT}" "$@"
}
