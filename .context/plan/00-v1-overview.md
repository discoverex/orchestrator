# v1.0.0 Refactor Program Overview

## Objective
v1.0.0 릴리즈 전 코드베이스를 운영 가능한 구조로 정리한다.

핵심 목표:
1. `src` 패키지 구조 정리 및 엄격한 헥사고널 아키텍처 준수
2. `scripts`/`bin` 흐름-구현 분리
3. 테스트 재구성(기능/범위 중심) 및 중복 제거
4. 문서 최신화(개념/경로/인증/노드 운영/간단 e2e)

## Scope Split (4 phases)
1. Phase 1: src hexagonal refactor + explorer 제거
2. Phase 2: scripts/bin modularization
3. Phase 3: pytest reorganization
4. Phase 4: docs refresh + release gate package

## Branch Strategy
- Base: `dev`
- Branches:
  - `ref/v1-src-hexagonal`
  - `ref/v1-scripts-bin-modularization`
  - `test/v1-pytest-reorg`
  - `docs/v1-doc-refresh`

Branch initialization:
- Empty intro commit required:
  - `chore: introduce <branch-name> branch`

Merge strategy:
- `git merge --no-ff <branch> -m "chore: merge <branch> into dev"`

## Architectural Non-Negotiables
- Domain layer must not depend on frameworks/adapters.
- Application layer depends only on domain + ports.
- Adapters depend on ports and external SDKs.
- Entrypoints/composition perform wiring only.
- No direct SDK calls from flow/business use-cases.

## Public Interface Policy
- `bin/project` and `bin/remote` command contracts are preserved.
- Internal structure may change.
- `storage_explorer` endpoints and env vars are removed in v1.0.0.

## Global Done Criteria
- All phase checklists complete.
- `uvx ruff check .` pass.
- `uv run pytest` pass.
- Local e2e core 1회 + remote e2e(dry-run prune) 1회 pass.
- Evidence artifacts linked in release notes.
