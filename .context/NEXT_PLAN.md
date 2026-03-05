# NEXT PLAN (Execution Verification Matrix)

## Objective
- Validate the new operating model end-to-end:
  - VM: Prefect server + VM-local Postgres + maintenance (flush/prune)
  - Local: storage-node as analysis/long-term SSOT target
  - Data path: register -> worker execute -> artifact upload -> run state on Prefect -> flush snapshot -> prune VM history

## Current State
- Implemented:
  - `infra/stacks/prefect-server`: `prefect-db`, `prefect-server`, `prefect-maintenance`, `cloudflared`
  - New scripts:
    - `scripts/ops/prefect_flush_completed.py`
    - `scripts/ops/prefect_prune_completed.py`
    - `scripts/ops/prefect_maintenance_loop.sh`
  - CLI:
    - `project prefect flush`
    - `project prefect prune`
  - CD/secret templates updated for Prefect-only deployment and runtime `.ci.env`

## Test Scope
### 1) Unit tests (core logic)
- `tests/test_prefect_flush.py`
  - cursor semantics (seen/advance/save/load)
  - dry-run behavior (no upload, no cursor write)
- `tests/test_prefect_prune.py`
  - completed+cutoff filter payload correctness
  - `--apply` delete call behavior

### 2) Smoke tests (single-host functional)
- Start Prefect stack:
  - `docker compose --env-file infra/stacks/prefect-server/.env -f infra/stacks/prefect-server/docker-compose.yml up -d --build`
- Verify:
  - `prefect-server` health endpoint
  - `prefect-db` healthy
  - `project prefect flush` one-shot success
  - `project prefect prune --dry-run` success

### 3) E2E tests (flow path)
- Existing script (`scripts/e2e/e2e_orchestrator.sh`) already validates:
  - register -> deployment submission
  - worker pickup and flow completion
  - artifact upload and manifest verification
  - optional MLflow metadata path (`mlflow`/`full`)
- Gap to close:
  - add post-run verification step for Prefect flush snapshot object
  - add prune verification for stale run deletion policy

### 4) Full-path validation (ops-level)
- External access:
  - worker -> Prefect via CF Access
  - worker -> storage-gateway via CF Access
- Failure handling:
  - storage unavailable during flush: cursor must not advance
  - retry flush after recovery must export missed completed runs

## Acceptance Criteria
- Unit tests for flush/prune pass.
- Smoke commands pass with no manual patching.
- E2E `core` passes and artifacts are verifiable.
- New flush/prune verification steps pass.
- Last successful flush snapshot reproduces completed run details at that checkpoint.

## Execution Order
1. Run unit tests (`test_prefect_flush.py`, `test_prefect_prune.py`)
2. Run Prefect smoke stack checks
3. Run `scripts/e2e/e2e_orchestrator.sh --mode core`
4. Add and run flush/prune post-verification steps in E2E
5. Re-run full suite and update docs with final verified commands/output
