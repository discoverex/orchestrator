#!/usr/bin/env bash

run_ops_connect() {
  load_remote_env
  require_remote_env
  exec ssh -i "${GITHUB_DEPLOY_KEY_PATH}" "${REMOTE_USERNAME}@${REMOTE_HOST}"
}
