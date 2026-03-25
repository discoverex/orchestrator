# Problem Statement

이 시스템은 설계된 실험을 여러 작업 단위로 나눠 실행하고, 각 작업의 산출물과
결과를 다시 하나의 실험 맥락으로 통합 관리하기 위해 존재한다.

## 1) Problem

실험성 workload는 보통 한 번의 단일 실행으로 끝나지 않는다.

- 하나의 실험은 여러 job으로 분해될 수 있다.
- 각 job은 서로 다른 입력, 코드 버전, 실행 환경, 재시도 이력을 가질 수 있다.
- job별 로그, 결과 파일, 중간 산출물, 메타데이터를 분리해 추적해야 한다.
- 동시에 그 결과를 다시 실험 단위로 묶어 해석할 수 있어야 한다.

문제는 이 요구가 보통 여러 시스템에 흩어진다는 점이다.

- 실행 제어는 scheduler가 담당한다.
- artifact는 object storage에 쌓인다.
- metric과 tag는 experiment tracker에 남는다.
- worker는 별도 런타임에서 job을 수행한다.

이렇게 분리된 요소를 한 흐름으로 연결하지 않으면, 특정 실험의 어떤 job이 어떤
코드와 입력으로 실행되었고 어떤 산출물을 남겼는지 일관되게 설명하기 어렵다.

## 2) What This Repository Treats As The Unit

이 저장소의 기본 실행 단위는 `job_spec_json`으로 표현되는 job이다.

- job은 engine, entrypoint, repo/ref, inputs, env를 가진다.
- 실행 시에는 Prefect flow run으로 materialize된다.
- 같은 job이라도 retry가 발생하면 `attempt` 단위로 결과가 분리된다.

즉, 이 시스템은 “실험 전체”를 직접 모델링하기보다, 실험을 구성하는 job들의
실행과 결과를 일관된 규칙으로 관리하는 쪽에 초점을 둔다.

## 3) Required Outcome

이 시스템이 보장해야 하는 핵심 결과는 다음과 같다.

- job이 재현 가능한 입력과 코드 버전으로 실행될 것
- 각 실행이 `flow_run_id`와 `attempt` 기준으로 식별될 것
- `stdout.log`, `stderr.log`, `result.json`과 추가 artifact가 durable하게 남을 것
- object storage와 MLflow metadata가 같은 실행을 가리키도록 연결될 것
- fixed worker, Colab worker 같은 서로 다른 실행 환경에서도 같은 계약을 유지할 것

## 4) How The Current Design Addresses It

현재 설계는 역할을 다음처럼 분리한다.

- Prefect: deployment, scheduling, retry, flow-run state 관리
- worker runtime: job validation, repo checkout, entrypoint 실행
- storage: presign/head control-plane과 object persistence
- MLflow: run metadata, params, metrics, tags 연결

이 분리를 통해 job 실행과 결과 관리의 관심사를 나누면서도, 아래 공통 식별자를
기준으로 통합 해석이 가능하도록 한다.

- `job_spec_json`
- `flow_run_id`
- `attempt`
- artifact object URI
- MLflow run/tag linkage

## 5) Related Documents

- 구조와 책임 분리: [topology.md](topology.md)
- end-to-end 흐름: [service-flow.md](service-flow.md)
- 실행 계약: [../contracts/execution.md](../contracts/execution.md)
- 서비스 인터페이스: [../contracts/service-interface.md](../contracts/service-interface.md)
