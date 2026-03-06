# Phase 3 - Pytest Reorganization

## Goal
테스트를 범위/기능 중심으로 재구성하고, 중복 및 혼합 책임 파일을 정리한다.

## Current Pain Points
- Large mixed test files (e.g., `tests/test_storage_gateway.py`)
- Script-import style tests with overlapping assertions
- Architecture/contract/unit 경계 불명확

## Target Layout
- `tests/unit/`
- `tests/integration/`
- `tests/contract/`
- optional `tests/e2e/` (smoke wrappers)
- Shared fixtures:
  - `tests/conftest.py`
  - `tests/fixtures/*.py`

## Reorganization Tasks
1. Split >200-line tests by feature behavior.
2. Move unrelated cases out of same file.
3. Merge duplicated scenarios into parametrized tests.
4. Normalize naming: `test_<feature>_<behavior>.py`.

## Mandatory Adjustments
- Remove explorer-specific tests.
- Update path-based script import tests to new module paths after Phase 2.

## Test Plan
- `uv run pytest tests/unit`
- `uv run pytest tests/integration`
- `uv run pytest tests/contract`
- `uv run pytest`

## Exit Criteria
- Test directory structure reflects scope boundaries.
- No obsolete explorer assertions.
- Full suite passes with stable runtime.
