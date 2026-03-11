#!/usr/bin/env bash

run_observability_workers() {
  run_python_tool "${OBSERVABILITY_WORKERS_SCRIPT}" "$@"
}
