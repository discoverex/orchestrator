# Orchestrator

설계된 실험을 여러 작업 단위로 분해해 실행하고, 각 작업의 산출물과 결과를
통합 관리하는 orchestration 저장소다. 현재 코드 기준으로는 Prefect를 실행
제어면으로 사용하고, worker가 job을 수행하며, storage와 MLflow가 artifact와
result metadata를 연결한다.

## Core Capabilities

- 실험을 job 단위로 분해해 Prefect deployment와 flow run으로 실행
- `repo` mode와 `inline` mode를 모두 지원하는 worker runtime 제공
- `flow_run_id` / `attempt` 기준의 로그, 결과, artifact 추적
- storage presign 경유 artifact 업로드와 object persistence 관리
- MLflow를 통한 run metadata, tag, metric 연계
- fixed worker와 Colab worker를 같은 실행 모델로 운영

## Stack

- Orchestration: Prefect
- Language and runtime: Python 3.11
- API and service layer: FastAPI, Uvicorn
- Artifact persistence: MinIO
- Experiment metadata: MLflow
- Packaging and dependency management: `uv`
- Container and local ops: Docker, Docker Compose
- Remote worker mode: Google Colab worker
- Auth and gateway boundary: Cloudflare Access, `worker_router`

## Directory Structure

- `src/`
  - `flows/`: worker runtime flow, engine run flow, job spec parsing
  - `runner/`: repo checkout, entrypoint execution, MLflow proxy
  - `storage/`: storage service, adapters, HTTP interface, MinIO integration
  - `worker_router/`: worker-facing storage/MLflow gateway
  - `deployments/`: Prefect deployment registration logic
  - `common/`: Prefect, Cloudflare, schema 공통 코드
- `scripts/`
  - `prefect/`, `storage/`, `worker/`, `register/`: 운영 CLI usecase 구현
  - `e2e/`: 로컬/원격 검증 흐름
  - `observability/`: smoke check와 Prefect 진단 도구
  - `ops/`: 원격 운영과 maintenance 보조 스크립트
- `infra/`
  - `stacks/`: `prefect-server`, `storage-node`, `register`, `worker` 스택 정의
  - `images/`: runtime image와 entrypoint 정의
- `docs/`
  - `concepts/`: 배경, 문제 정의, 구조, 흐름
  - `guides/`: 운영 절차
  - `contracts/`: 실행/서비스/등록 계약
  - `reference/`: CLI reference
- `deployments/`
  - `e2e/`: canonical deployment naming과 compat alias 정의
- `tests/`
  - `contract/`, `integration/`, `unit/`: 문서/스크립트/서비스 회귀 검증

## Documentation Map

### Concepts

- [Problem Statement](docs/concepts/problem-statement.md): 실험을 job으로 분해하고 결과를 통합 관리해야 하는 이유
- [Conceptual Topology](docs/concepts/topology.md): 시스템 노드와 책임 분리
- [Service Flow](docs/concepts/service-flow.md): register -> submit -> execute -> persist 흐름
- [Auth Model](docs/concepts/auth-model.md): 인증 경계와 secret 배치 원칙
- [State Machine](docs/concepts/state-machine.md): Prefect 상태와 retry 의미

### Guides

- [Local Quickstart](docs/guides/quickstart-local.md): 로컬 검증 절차
- [Colab Worker Setup](docs/guides/setup-colab-worker.md): Colab worker bootstrap/운영
- [Storage Node Setup](docs/guides/setup-storage.md): storage node 배포/검증
- [Prefect Server Setup](docs/guides/setup-prefect.md): Prefect node 배포/검증

### Contracts

- [Engine Implementation](docs/contracts/engine-implementation.md): 엔진 실행 계약
- [Execution Contract](docs/contracts/execution.md): flow input, retry, 산출물 계약
- [Service Interface](docs/contracts/service-interface.md): 서비스 간 인터페이스 계약
- [Engine Registration](docs/contracts/registration/overview.md): 외부 엔진 등록 요구사항

### Reference

- [CLI Reference](docs/reference/cli.md): `bin/cli` 명령 레퍼런스
- [E2E Deployment Spec](deployments/e2e/README.md): canonical deployment naming과 compat alias

## Validation

- Tests: `uv run pytest`
- Lint: `uv run ruff check .`
