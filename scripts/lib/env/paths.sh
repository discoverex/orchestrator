#!/usr/bin/env bash

RUNTIME_ROOT_DEFAULT="$(cd "${ROOT_DIR}/.." && pwd)/runtime"
RUNTIME_ROOT="${RUNTIME_ROOT:-${RUNTIME_ROOT_DEFAULT}}"

WORKER_RUNTIME_DIR="${RUNTIME_ROOT}/worker"
WORKER_CHECKPOINT_DIR="${RUNTIME_ROOT}/worker/checkpoints"
WORKER_REPO_CACHE_DIR="${RUNTIME_ROOT}/worker/repo_cache"

LOCAL_COMPOSE="${ROOT_DIR}/scripts/e2e/docker-compose.local.test.yml"
STORAGE_ENV="${ROOT_DIR}/infra/stacks/storage-node/.env"
STORAGE_COMPOSE="${ROOT_DIR}/infra/stacks/storage-node/docker-compose.yml"
REGISTER_ENV="${ROOT_DIR}/infra/stacks/register/.env"
REGISTER_COMPOSE="${ROOT_DIR}/infra/stacks/register/docker-compose.yml"
WORKER_FIXED_ENV="${ROOT_DIR}/infra/stacks/worker/fixed/.env"
WORKER_FIXED_COMPOSE="${ROOT_DIR}/infra/stacks/worker/fixed/docker-compose.yml"
PREFECT_ENV="${ROOT_DIR}/infra/stacks/prefect-server/.env"
PREFECT_COMPOSE="${ROOT_DIR}/infra/stacks/prefect-server/docker-compose.yml"

PREFECT_BUILD_DOCKERFILE="${ROOT_DIR}/infra/images/prefect-server.Dockerfile"
BASE_BUILD_DOCKERFILE="${ROOT_DIR}/infra/images/base.Dockerfile"

PREFECT_FLUSH_SCRIPT="/opt/orchestrator/scripts/ops/prefect_flush_completed.py"
PREFECT_PRUNE_SCRIPT="/opt/orchestrator/scripts/ops/prefect_prune_completed.py"
GPU_INSTALL_SCRIPT="${ROOT_DIR}/scripts/ops/install_nvidia_container_toolkit.sh"
PREFECT_VM_BOOTSTRAP_SCRIPT="scripts/ops/prefect_vm_bootstrap.sh"
SUBMIT_ROUTER_SCRIPT="${ROOT_DIR}/scripts/ops/prefect_submit_router.py"
OBSERVABILITY_WORKERS_SCRIPT="${ROOT_DIR}/scripts/observability/prefect_list_workers.py"
OBSERVABILITY_FIXED_DUMMY_SMOKE_SCRIPT="${ROOT_DIR}/scripts/observability/prefect_fixed_dummy_smoke.py"
