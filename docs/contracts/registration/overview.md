# Engine Registration Requirements

이 문서는 외부 엔진 저장소가 등록과 실행을 위해 충족해야 할 요구사항의
인덱스다. 세부 실행 규칙, 인증 경계, artifact 정책은 하위 계약 문서로 분리한다.

## 1) Scope

이 문서의 대상은 외부 엔진 저장소다. 운영 절차는 가이드 문서를 따르고,
이 문서는 등록 입력과 호환성 요구사항만 정의한다.

외부 엔진 저장소 책임:

- register 가능한 Prefect flow callable 제공
- orchestrator가 기대하는 parameter schema 유지
- worker가 실행 가능한 repo layout과 dependency 유지
- engine process의 런타임 동작 보장

이 저장소 책임:

- deployment 생성과 갱신
- pool/queue routing
- `repo` mode checkout과 runtime env 주입
- artifact upload orchestration
- storage/MLflow access mediation

## 2) Required Deliverables

### Registerable flow callable

- 엔진 repo는 `path/to/file.py:callable_name` 형식의 flow entrypoint를 제공해야 한다.
- 이 값은 등록 시 `REGISTER_FLOW_ENTRYPOINT`로 전달된다.

### Visible source root

- 등록 runtime이 flow source를 읽을 수 있는 고정 경로를 제공해야 한다.
- 이 값은 `REGISTER_FLOW_SOURCE`로 전달된다.

### Compatible flow signature

- common worker-runtime과 호환하려면 live flow signature가 아래 parameter를 받아야 한다.
- `job_spec_json`
- `resume_key` optional
- `checkpoint_dir` optional
- 기준 flow는 [src/flows/worker_runtime/flow.py](../../../src/flows/worker_runtime/flow.py)다.

### Job spec compatibility

- `job_spec_json`은 [src/flows/job_spec.py](../../../src/flows/job_spec.py) 검증을 통과해야 한다.
- 예시는 [job_spec.repo.example.json](job_spec.repo.example.json)을 따른다.

### Worker execution compatibility

- 엔진은 [../engine-implementation.md](../engine-implementation.md) 실행 계약을 만족해야 한다.
- 기본 조건은 non-interactive entrypoint, temp workdir 실행, worker env 허용, direct object-store credential 비의존이다.

## 3) Registration Inputs

엔진 팀이 전달해야 할 값:

- `REGISTER_FLOW_SOURCE`
- `REGISTER_FLOW_ENTRYPOINT`
- optional `REGISTER_DEPLOYMENT_VERSION`

운영 측이 결정하는 값:

- `PREFECT_API_URL`
- `PREFECT_WORK_POOL`
- deployment names
- queue names
- access headers와 service tokens

핸드오프 예시는 [register.engine.env.example](register.engine.env.example)을 따른다.

## 4) Companion Documents

- runtime env와 인증 경계:
  [runtime-auth-and-env.md](runtime-auth-and-env.md)
- durable artifact 정책:
  [artifact-persistence-contract.md](artifact-persistence-contract.md)
- worker-managed output directory:
  [worker-managed-output-directory-contract.md](worker-managed-output-directory-contract.md)
- submit payload 예시:
  [job_spec.repo.example.json](job_spec.repo.example.json)
- engine artifact manifest 예시:
  [engine-artifacts.manifest.example.json](engine-artifacts.manifest.example.json)
- 서비스 간 인터페이스 계약:
  [../service-interface.md](../service-interface.md)

## 5) Naming Defaults

- canonical flow name과 deployment 이름은 [deployments/e2e/README.md](../../../deployments/e2e/README.md)를 따른다.
- 현재 코드에는 compat alias가 남아 있으므로, legacy naming이 필요하면 deployment catalog를 직접 확인한다.
- custom flow/deployment naming은 지원되지만, 기본 observability/routing 스크립트는 canonical naming을 전제로 한다.
