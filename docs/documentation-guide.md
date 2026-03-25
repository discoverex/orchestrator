# Documentation Guide

이 문서는 저장소 전체 문서 체계의 기준이다. 새 문서를 추가하거나 기존 문서를
수정할 때는 이 문서의 책임 분리 원칙을 따른다.

## 1) Core Principles

- 각 문서는 하나의 책임만 가져야 한다.
- 같은 내용을 여러 문서에 반복하지 말고, 책임 문서 하나에만 두고 나머지는 링크로 연결한다.
- 코드 경로, CLI, env var, API path는 실제 저장소 기준으로 적는다.
- 운영 상태 보고, 임시 메모, 중간 계획 문서는 정식 문서 트리에 두지 않는다.
- 문서는 한국어를 기본으로 하되, 코드 심볼과 경로, 명령어, env var는 원문 그대로 유지한다.

## 2) Document Map

문서 진입점은 아래 순서를 따른다.

1. `README.md`
2. `docs/concepts/`
3. `docs/guides/`
4. `docs/contracts/`
5. `docs/reference/`
6. `deployments/e2e/README.md`

## 3) Root README Scope

`README.md`는 저장소 전체의 단일 진입점이다.

반드시 포함할 내용:

- 프로젝트 소개
- 핵심 기능
- 기술 스택
- 디렉터리 구조
- 문서 맵
- 기본 검증 명령

넣지 말아야 할 내용:

- 긴 운영 절차
- 상세 API 계약
- 배포 catalog의 세부 naming 표
- 임시 상태 보고

README는 “무엇을 하는 저장소인지”와 “어디를 읽어야 하는지”만 빠르게 설명해야 한다.

## 4) `docs/concepts/` Scope

`docs/concepts/`는 배경, 문제 정의, 구조, 흐름 같은 이해 문서만 둔다.

포함할 내용:

- 왜 이 시스템이 필요한지
- 시스템이 어떤 문제를 푸는지
- 주요 노드와 책임 분리
- end-to-end 개념 흐름
- 상태 전이의 의미
- 인증 경계의 원칙

포함하지 말아야 할 내용:

- 상세 운영 명령
- step-by-step 배포 절차
- API request/response 규범
- 파일별 세부 구현 설명
- 감사 결과, 체크리스트, 임시 cutover 메모

각 문서 책임:

- `problem-statement.md`
  - 문제 정의와 목표만 다룬다.
  - 실험, job, 산출물, 결과 통합 관리의 필요성을 설명한다.
- `topology.md`
  - 현재 시스템의 노드와 책임 분리만 다룬다.
  - 배경 설명은 `problem-statement.md`로 링크한다.
- `service-flow.md`
  - register -> submit -> execute -> persist 흐름만 다룬다.
  - 상세 계약과 운영 절차는 링크로 넘긴다.
- `auth-model.md`
  - 인증 경계와 secret 분리 원칙만 다룬다.
- `state-machine.md`
  - Prefect 상태, retry, attempt 의미만 다룬다.

## 5) `docs/guides/` Scope

`docs/guides/`는 운영 절차와 how-to만 둔다.

포함할 내용:

- 실제 실행 순서
- 필요한 명령
- 준비해야 할 env/config
- 검증 방법
- 운영상 주의점

포함하지 말아야 할 내용:

- 시스템 배경 설명
- 서비스 간 계약 정의
- 동일 내용을 다른 guide에 반복하는 설명

각 문서는 하나의 운영 대상만 가져야 한다.

예시:

- `quickstart-local.md`: 로컬 검증 절차만
- `setup-storage.md`: storage node 배포/검증만
- `setup-prefect.md`: Prefect node 배포/검증만
- `setup-colab-worker.md`: Colab worker bootstrap/운영만

## 6) `docs/contracts/` Scope

`docs/contracts/`는 코드와 외부 인터페이스 사이의 규범 문서만 둔다.

포함할 내용:

- flow input과 output 계약
- 서비스 간 API 계약
- artifact layout과 persistence 규칙
- engine registration과 runtime contract
- worker가 보장하는 실행 규칙

포함하지 말아야 할 내용:

- 운영 runbook
- 아키텍처 배경 설명
- 상세 troubleshooting 절차
- 상태 보고

문서는 “무엇이 반드시 성립해야 하는가”를 기준으로 써야 한다.

상위 문서 책임:

- `execution.md`
  - flow input, retry, result/artifact 산출물 계약
- `service-interface.md`
  - 서비스 간 HTTP/storage/MLflow 인터페이스 계약
- `engine-implementation.md`
  - engine process가 만족해야 하는 실행 계약

`docs/contracts/registration/` 책임:

- 외부 엔진 등록과 실행 호환성에 필요한 계약만 둔다.
- operator 절차가 아니라 engine handoff 기준을 정의한다.

세부 책임:

- `overview.md`
  - registration 입력과 관련 문서 인덱스
- `runtime-auth-and-env.md`
  - worker가 주입하는 env와 인증 경계
- `artifact-persistence-contract.md`
  - durable artifact 정책
- `worker-managed-output-directory-contract.md`
  - engine artifact manifest와 upload 규칙
- `*.example.*`
  - 예시 payload, env, manifest만 제공

## 7) `docs/reference/` Scope

`docs/reference/`는 빠르게 찾아보는 reference만 둔다.

포함할 내용:

- CLI usage
- 고정 형식의 표나 옵션 요약
- 다른 문서에서 반복하기 싫은 짧은 참조 정보

포함하지 말아야 할 내용:

- 감사 보고서
- 작업 체크리스트
- 임시 운영 결과
- 장문의 설계 설명

현재 기준으로 `docs/reference/cli.md`만 유지한다.

## 8) `deployments/e2e/` Scope

`deployments/e2e/README.md`는 deployment naming의 source of truth 역할만 한다.

포함할 내용:

- canonical flow name
- canonical deployment names
- 코드에 남아 있는 compat alias
- 관련 YAML의 역할

포함하지 말아야 할 내용:

- 운영 절차
- auth/env 설명
- worker/runtime 상세 설명

## 9) Cross-Link Rules

- 개념 문서에서 운영 절차가 필요하면 `docs/guides/`로 링크한다.
- 가이드에서 배경 설명이 필요하면 `docs/concepts/`로 링크한다.
- 가이드에서 강한 규범이 필요하면 `docs/contracts/`로 링크한다.
- README에서는 각 문서군의 대표 문서로만 연결하고, 세부 구현 설명은 하위 문서에 둔다.
- deployment naming은 `deployments/e2e/README.md` 한 곳을 기준으로 삼고, 다른 문서는 링크만 건다.

## 10) What Not To Add

추가하지 말아야 할 문서 유형:

- audit report
- migration note
- temporary plan
- hand-edited status page
- checklist only 문서

이런 내용이 필요하면:

- 실제 규범으로 승격해 계약/가이드 문서에 흡수하거나
- 정식 문서 트리 밖에서 관리한다.
