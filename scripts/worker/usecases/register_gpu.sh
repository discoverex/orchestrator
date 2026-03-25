#!/usr/bin/env bash

run_worker_register_gpu() {
  compose_register run --rm register "$@"
}
