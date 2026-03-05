# prefect

## 목적

- 기존 레포(2번째 업무지시서까지 완료 상태: scheduler/worker/storage 분리 + 경계 정리)를 Prefect 기반 오케스트레이션으로 전환
- “바퀴 재발명” 최소화
  - 스케줄링/상태/재시도/관측(기본)은 Prefect가 담당
  - 레포는 실행 런너(엔진 실행) + 스토리지 게이트웨이(presign) + Prefect Flow/Deployment 정의에 집중

- 요구사항(정석/권장 기준)
  - 단일 GPU 원격 실행
  - 일회용(짧은 수명) 워커(Colab 중심, outbound 연결)
  - 스토리지 노드 별도(로컬 MinIO SSOT)
  - 워커는 MinIO 키 미보유(B안: presigned URL)
  - 코드 버전 고정(ref 입력 가능, 실행은 commit 고정)

---

## 핵심 전환 원칙

- 기존 “Scheduler(잡 큐/할당/상태 머신)” 기능은 Prefect로 치환
- 기존 Worker는 “Prefect Worker + Runner(실행기)”로 재정의
- Storage는 “Data Plane 서비스(스토리지 게이트웨이)”로 유지/강화

---

## 용어/모델 명명 규칙( Prefect 권장 용어로 전환 )

### 기존 용어 → 신규 용어

- Job / JobSpec → Flow(실행 단위) + Deployment(배포/파라미터 템플릿)
- job_id → flow_run_id (Prefect가 발급)
- run_id(시도 단위) → task_run_id 또는 (flow_run_id + attempt)
- SchedulerService / Assignment / Lease → Work Pool / Work Queue / Worker (Prefect 개념)
- Worker enroll/JWT → Prefect API 인증(PREFECT_API_KEY 또는 self-host 인증 방식)

### 남겨야 하는 커스텀 모델(최소)

- CodeRef
  - repo_url
  - ref(입력)
  - resolved_commit(고정)
  - entrypoint

- ArtifactManifest
  - outputs_prefix
  - artifacts: (kind, object_key, put_url, get_url(optional))
  - ttl_seconds

---

## 레포 구조 변경(권장)

### 제거/축소

- src/scheduler/\*
  - “잡 큐/할당/상태 머신/워커 등록” 관련 코드는 삭제 또는 deprecate
  - 남길 경우: prefect 배포/등록을 돕는 thin CLI 정도로 축소

### 유지/강화

- src/storage/\*
  - 역할 재정의: storage gateway(=presign api) + minio adapter
  - 워커/flow는 storage gateway API만 호출

### 재구성(새로 추가)

- src/flows/
  - Prefect Flow 정의(엔진 실행 플로우, 검증 플로우 등)

- src/deployments/
  - Deployment 빌드/등록 CLI(환경별: dev/prod)

- src/runner/
  - 실제 실행기: git checkout(커밋 고정) → entrypoint 실행 → 로그/아티팩트 파일 생성
  - 실행기는 “로컬 파일 시스템”만 다루고, 업/다운로드는 storage client로 위임

- src/blocks/ (선택)
  - Prefect Block으로 storage gateway endpoint, 기본 TTL, bucket/prefix 규칙 등 설정 캡슐화

---

## Prefect 구성(필수 결정 고정)

### Orchestrator(권장)

- Prefect Cloud 우선
  - Colab 워커가 외부로 붙는 구성이 가장 단순

- self-host가 필요하면
  - Prefect 서버 + 메타DB(Postgres)는 VM(클라우드)에 둔다(로컬 SSH 터널로 DB를 빼지 않음)

### Work Pool

- pool 이름: colab-gpu
- worker 타입: process(Colab에서 docker 의존 제거)
- Work Queue는 필요 시만(우선은 1개)

---

## Storage(B안: Presigned URL) 구성

### 로컬 Storage Node

- MinIO는 로컬에서 운영
- 외부 접근은 Cloudflare Tunnel로 제공(HTTPS)
- Storage Gateway API 제공(자체 FastAPI 등)
  - 기능: presigned PUT/GET 발급, object key 규칙 강제, (선택) 업로드 완료 확인(head)

### 워커 권한

- 워커는 MinIO access key/secret을 절대 받지 않음
- 워커는 presigned URL만 사용

---

## 오브젝트 네이밍 규칙(필수 고정)

- outputs_prefix 기본:
  - jobs/{flow_run_id}/attempt-{attempt}/

- 표준 아티팩트
  - stdout.log
  - stderr.log
  - result.json (요약 메타)
  - artifacts.json (manifest)
  - 기타 산출물은 kind 기반 서브디렉터리 허용

---

## Flow 설계(기능 단위)

### 공통 Flow: engine_run_flow

- 입력 파라미터
  - repo_url
  - ref(branch/tag/sha)
  - entrypoint
  - inputs_ref(list)
  - outputs_prefix(optional; 기본은 규칙 생성)

- 태스크 구성(권장 순서)
  1. resolve_commit
     - ref가 branch/tag면 resolved_commit 확정
     - resolved_commit은 이후 불변

  2. prepare_manifest
     - storage gateway에 presign 요청
     - stdout/stderr/result 등 최소 셋에 대해 PUT URL 확보

  3. fetch_inputs
     - 필요 시 input도 presigned GET으로 수신(또는 캐시 사용)

  4. run_entrypoint
     - runner가 git checkout(resolved_commit) + entrypoint 실행
     - sandbox에서만 작업

  5. upload_outputs
     - runner 결과물 파일들을 presigned PUT으로 업로드

  6. record_links
     - Prefect task 결과로 outputs_prefix + 핵심 링크(URI) 반환

### Retry 정책

- Prefect의 retry/backoff 사용
- attempt 번호는 Prefect retry 횟수와 동기화(또는 별도 계산)

---

## 기존 코드 이관/삭제 지시

### 1) scheduler 패키지 처리

- 삭제 대상
  - job 큐/할당/lease/heartbeat/state machine
  - worker enroll/JWT

- 대체
  - Prefect Work Pool/Worker/FlowRun으로 대체

- 남길 경우(옵션)
  - deployment 등록/버전 pinning/환경 설정만 담당하는 CLI로 축소
  - 패키지명은 scheduler 유지 금지 → deployments 또는 prefect_cli로 변경

### 2) worker 패키지 처리

- Prefect worker(프로세스)는 Prefect가 제공
- 기존 worker 코드는 “runner + storage client”로 분해
  - runner: git/entrypoint 실행만
  - storage client: presign API 호출 + PUT/GET 수행

- 기존 worker의 poll/ack/complete/fail/heartbeat API 코드는 제거

### 3) storage 패키지 처리

- 유지 + 강화
  - presign API 정식화
  - TTL, key 규칙, 크기 제한(가능하면) 명시
  - (선택) 완료 확인 endpoint 추가

---

## 보안/토큰

- Prefect 인증
  - Cloud: PREFECT_API_KEY 사용
  - self-host: 해당 방식에 따름

- Storage gateway 인증(권장)
  - 간단한 bearer token(별도) 또는 Cloudflare Access 적용
  - presign 발급은 반드시 인증 필요

---

## 마이그레이션 단계(권장 순서)

1. 디렉토리 재구성
   - flows/, deployments/, runner/ 추가
   - scheduler/ deprecate 폴더로 이동 또는 제거 계획 수립

2. 모델/용어 rename
   - Job/Assignment/Lease 제거
   - CodeRef, ArtifactManifest 도입
   - job_id/run_id 표기는 flow_run_id/task_run_id로 치환

3. storage gateway presign API 고정
   - PUT/GET presign
   - object key 규칙
   - TTL 기본값

4. runner 구현 정리
   - git checkout(resolved_commit)
   - entrypoint 실행
   - stdout/stderr 캡처
   - 결과물 파일 표준 위치 생성

5. Prefect Flow 작성
   - resolve_commit → manifest → run → upload → record

6. Deployment 등록
   - colab-gpu work pool에 배포
   - ref는 입력 파라미터로 허용

7. Colab 런북
   - Prefect worker 시작
   - GPU 확인
   - 단일 flow run 실행

8. 통합 테스트
   - 성공/실패/retry 시 attempt 경로 분리 확인
   - MinIO에 로그/아티팩트 업로드 확인
   - Prefect UI/메타에서 outputs_prefix 링크 확인

---

## 완료 조건(Definition of Done)

- Prefect 기반으로 단일 GPU 실행이 가능
- Colab 일회용 워커가 work pool에 붙어서 실행 가능
- MinIO 키는 스토리지 노드에만 존재
- 워커는 presigned URL로만 업/다운로드
- ref(branch) 입력해도 실행은 resolved_commit으로 고정
- retry 시 동일 commit 유지 + attempt별 prefix 분리
- 기존 scheduler의 큐/할당/상태 머신 코드는 제거 또는 배포/등록 CLI로 축소 완료

---

## 주의(실수 방지)

- Prefect 메타 DB를 로컬로 빼서 SSH 터널로 연결하지 않음(지연/끊김에 취약)
- MinIO 콘솔(9001)은 외부 노출 금지 또는 강력 보호(Cloudflare Access)
- presign URL TTL 만료 대비: 업로드 실패 시 재발급 재시도 정책 포함
