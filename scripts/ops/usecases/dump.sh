#!/usr/bin/env bash

run_ops_dump() {
  load_remote_env
  local output_file
  output_file="dump_$(date +%Y%m%d_%H%M%S).sql"
  echo "Dumping remote database to ${output_file}..."
  remote_exec "docker exec postgres pg_dump -U gtrpgm -d gtrpgm" > "${output_file}"
  echo "Success: Dump saved to ${output_file}"
}
