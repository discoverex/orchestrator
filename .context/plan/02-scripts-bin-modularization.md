# Phase 2 - scripts/bin Modularization

## Goal
엔트리 스크립트는 흐름만 보여주고, 재사용 구현은 라이브러리 파일로 분리한다.

## In Scope
- `bin/project`
- `bin/remote`
- `scripts/e2e/e2e_orchestrator.sh`
- `scripts/e2e/remote_prefect_storage_e2e.sh`
- `scripts/e2e/verify_remote_chain.py`
- `scripts/ops/prefect_flush_completed.py`

## Target Structure
- `bin/lib/`
  - `common.sh`
  - `compose.sh`
  - `runtime.sh`
  - `e2e.sh`
  - `remote.sh`
- `scripts/e2e/lib/`
  - step helpers / diagnostics / validations
- `scripts/ops/lib/`
  - shared prefect http/env helpers

## Refactor Rules
- Keep existing command-line flags and defaults intact.
- Centralize env loading and error handling.
- Replace repeated shell fragments with helper functions.
- Keep entry scripts readable as sequential flow.

## Python helper split
- Break large verifier modules into composable units:
  - API client
  - assertion/check functions
  - CLI arg parsing

## Test Plan
- `bash -n bin/project bin/remote scripts/e2e/*.sh scripts/ops/*.sh`
- `uv run pytest tests/test_remote_chain_verify.py tests/test_prefect_flush.py tests/test_prefect_submit_router.py`
- Add/adjust tests for shared helper behavior.

## Exit Criteria
- Entry scripts significantly reduced in branching complexity.
- Shared logic extracted and unit-tested.
- No behavior regression in existing CLI contract tests.
