#!/usr/bin/env bash

run_ops_postgres() {
  load_remote_env
  remote_exec "docker exec -it postgres psql -U gtrpgm -d gtrpgm"
}
