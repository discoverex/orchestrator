#!/usr/bin/env bash

if [[ -z "${ROOT_DIR:-}" ]]; then
  ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fi

source "${ROOT_DIR}/scripts/lib/assert.sh"
source "${ROOT_DIR}/scripts/lib/env/repo.sh"
source "${ROOT_DIR}/scripts/lib/env/paths.sh"
source "${ROOT_DIR}/scripts/lib/drivers/fs.sh"
source "${ROOT_DIR}/scripts/lib/drivers/compose.sh"
source "${ROOT_DIR}/scripts/lib/drivers/remote.sh"
source "${ROOT_DIR}/scripts/lib/drivers/python.sh"
