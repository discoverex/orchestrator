# Phase 1 - src Hexagonal Refactor

## Goal
`src` 패키지를 책임 기준으로 재배치하고, 200+ 라인 파일을 우선 분해한다.

## In Scope
- `src/flows/engine_run_flow.py` (230)
- `src/storage_gateway/main.py` (188, 구조 리팩터링)
- `src/storage_explorer/router.py` (285, 삭제)
- `src/storage/*`, `src/runner/*`, `src/deployments/*`

## Out of Scope
- CLI 인터페이스 변경
- 신규 기능 추가

## Mandatory Removals
- Remove package: `src/storage_explorer`
- Remove explorer wiring from `src/storage_gateway/main.py`
- Remove explorer exports/import references in `src/storage*`

## Module Plan
### flows
- Split into:
  - `src/flows/engine_run/flow.py` (entry)
  - `src/flows/engine_run/tasks.py`
  - `src/flows/engine_run/usecases.py`
  - `src/flows/engine_run/models.py`
- Keep compatibility import at `src/flows/engine_run_flow.py` if needed during migration window.

### storage_gateway
- Introduce:
  - `src/storage_gateway/app.py` (factory)
  - `src/storage_gateway/deps.py`
  - `src/storage_gateway/routes.py`
  - `src/storage_gateway/auth.py`
- `main.py` becomes thin entrypoint only.

### hexagonal enforcement
- Add architecture tests verifying forbidden imports.
- Update existing architecture test to exclude explorer and validate new boundaries.

## Risks
- Hidden runtime dependency on explorer route.
- Flow import path regressions (`entrypoint` used by register).

## Test Plan
- `uv run pytest tests/test_storage_architecture.py`
- `uv run pytest tests/test_engine_run_flow.py tests/test_checkpoint_store.py`
- `uv run pytest tests/test_prefect_deploy_script.py tests/test_register_multi_deploy.py`

## Exit Criteria
- No src file above 200 lines unless explicitly exempted with rationale in PR.
- Explorer code/route/env fully removed.
- Architecture tests enforce hexagonal boundaries.
