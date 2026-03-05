# orchastrator design

## 목적

- Colab 중심(일회용/공개망) 워커들이 클라우드 상 스케줄러에 HTTPS로 접속해 Job을 가져가 실행하고, 결과/로그/아티팩트를 MinIO에 적재하는 최소 실행 플랫폼(MVP) 구축
- 인프라 레포는 도메인 캐논(Scene/Goal/Region 등)을 모름
  - 오직 Execution Contract(잡 스펙/상태/리소스/아티팩트 참조)만 다룸

## 핵심 제약/가정

- 워커: Colab 메인, 동적 IP, 일회용 세션 많음, 인바운드 포트 오픈 불가 가정
- 네트워크: 공개망, 통신은 HTTPS only
- 잡: 단일 GPU 기반(멀티 GPU 잡은 MVP 범위 제외)
- 스토리지: MinIO가 SSOT, Google Drive는 캐시/부트스트랩 보조 용도
- 큐/상태 저장: Postgres(스케줄링 큐 포함)

## 설계 원칙

- Pull 모델: 워커가 스케줄러에 poll → 스케줄러가 job 할당
- at-least-once 실행 + 멱등 상태 전이(idempotent)
- 상태 머신/정책을 문서로 고정 후 구현
- 헥사고널 아키텍처 준수
  - Port(인터페이스) 선 정의 → Adapter(구현) 후

- src 패턴 + 패키지 분리
  - src/scheduler/_, src/worker/_

- 단일 책임 + 파일 200줄 이하
  - 200줄 초과 시 역할에 따라 분해
  - **init**.py로 외부 노출 API 최소화(캡슐화)

- 관측 가능성: 구조화 로그(JSON) + correlation_id(job_id/run_id)

## 범위(MVP)

- 스케줄러
  - 워커 등록(enroll) + 세션 토큰 발급(JWT)
  - 워커 heartbeat 수집 및 worker_dead 처리
  - FIFO 기반 job 할당(자원 조건: gpu=1 고정)
  - retry 정책(max_retry, backoff, available_at 기반 재등장)
  - job 상태 전이(멱등)
  - 관리자용 최소 API(job submit, job cancel, 상태 조회)

- 워커
  - enroll → JWT 획득
  - 주기적 poll로 job 수신
  - job sandbox에서 실행(로컬/uv/venv 기반)
  - 표준 출력/에러/메타데이터 업로드
  - heartbeat/lease 연장
  - 완료/실패 보고(멱등)

- 저장소
  - Postgres: job/worker/assignment/event
  - MinIO: inputs/outputs/logs/reports
  - Google Drive: 선택적으로 enroll token 저장(권한 엄격) + 캐시

## 비범위(명시)

- 멀티 GPU 잡/분산 학습 스케줄링
- p2p 파일 전송
- pg_cron/unlogged table 최적화(추후)
- UI 대시보드(추후)

## 반드시 고정할 실행 계약(Execution Contract)

- Job은 도메인 캐논 대신 아래 메타만 가진다
  - job_id: UUID
  - job_type: string (예: generate/verify/train/eval 등, MVP에서는 분류만)
  - image_ref: (옵션) 컨테이너 이미지 해시/태그 또는 런타임 식별자
  - command: 실행 커맨드 배열
  - env: 키-값(민감정보 제외)
  - resources: { gpu: 1, vram_gb?: int }
  - inputs: URI 리스트(예: s3://bucket/path 또는 minio://)
  - outputs: URI prefix(업로드 목적지)
  - spec_ref: URI(원본 스펙 저장 위치)
  - max_retry: int (기본 3)
  - backoff_policy: (기본 고정)
  - created_at / available_at

## 상태 머신(문서로 박기)

### Job 상태

- pending: 대기(available_at <= now 인 것만 할당 대상)
- assigned: 특정 worker_id에 임시 할당(ack 대기)
- running: 워커가 ack 후 실행 중(heartbeat/lease 연장 필요)
- succeeded: 성공 완료
- failed: 영구 실패(max_retry 초과 또는 cancel)
- retrying: 실패 후 재시도 대기(available_at 미래)

### Worker 상태

- active: heartbeat 정상
- inactive: 명시적 종료/일시 비활성
- dead: heartbeat timeout

### 전이 규칙(핵심)

- pending → assigned: 스케줄러가 트랜잭션으로 1개 선택 후 worker_id 지정
- assigned → running: 워커가 ack 호출(멱등)
- running → succeeded: 완료 보고(멱등)
- running/assigned → retrying: 실패 보고 또는 lease/heartbeat timeout
- retrying → pending: available_at 도달 시 pending으로 재노출(또는 pending으로 두고 available_at만 사용)
- pending/assigned/running → failed: max_retry 초과 또는 cancel

## 시간/임계값(권장 기본값)

- heartbeat_interval: 15s
- worker_dead_timeout: 60s (마지막 heartbeat 기준)
- job_lease_seconds: 90s (heartbeat로 연장)
- poll_interval: 5~15s (워커가 랜덤 지터 포함)

## Retry 정책(권장)

- max_retry 기본 3
- backoff: 30s → 2m → 10m (고정)
- 실패 job은 FIFO 맨앞 삽입 금지
  - available_at 기반으로 큐에 재등장

- 영구 실패 시 permanently_failed로 마킹 + 원인/스택/리턴코드 보존

## 인증/보안(공개망 + 일회용 워커)

### enroll token

- 목적: 최초 워커 등록(짧은 기간/1회성)
- 저장: Google Drive에 저장 가능(짧은 문자열 OK)
  - 단, 권한 “나만”, 링크 공유 금지, 로그 출력 금지

- 흐름
  - 워커: POST /workers/enroll (enroll_token)
  - 스케줄러: worker_id 발급 + JWT(만료 6~24h 권장) 반환

### JWT

- 워커의 poll/heartbeat/ack/complete/fail 호출에 사용
- 스케줄러는 JWT 검증 + worker_id binding

### 최소 보안 수칙

- TLS 강제
- 요청/응답에서 토큰 마스킹(로그에 금지)
- 토큰 회수(revoke) API는 MVP에 optional(추후)

## 저장소/큐: Postgres 기반

### DB는 SSOT

- Job/Worker 상태, 할당, 이벤트는 DB가 권위
- 스케줄러 프로세스는 ‘정책 결정자’지만, 중복 할당 방지는 DB 트랜잭션으로 보장

### 큐 구현 개념(코드 제외)

- FIFO + available_at 조건 + 행 잠금(동시 워커 poll에서도 1개만 가져가게)
- 멱등 업데이트를 위해
  - job_id 기준 업데이트
  - 상태 전이 시 이전 상태 조건을 WHERE에 포함(optimistic)

## 스토리지: MinIO + Drive 캐시

### MinIO

- inputs/outputs/logs/reports의 SSOT
- URI 규칙
  - s3://{bucket}/{prefix}
  - 모든 job은 outputs_prefix를 가진다

### Google Drive(보조)

- enroll token 저장 가능
- 캐시 용도
  - 대용량 input을 Drive에 캐시해 Colab에서 재다운로드 비용 절감(선택)

- Drive는 SSOT 아님(미스 시 MinIO에서 복구)

## 로깅/관측

- JSON 구조화 로그
- 필수 필드
  - ts, level, service(scheduler|worker), worker_id, job_id, run_id, event, msg

- 워커는 stdout/stderr를 파일로 저장 후 MinIO 업로드
- 스케줄러는 상태 전이를 이벤트로 남김(테이블 또는 로그)

## 레포 구조(권장)

- repo/
  - README.md
  - AGENTS.md (규칙/컨벤션)
  - pyproject.toml (uv)
  - src/
    - scheduler/
      - **init**.py
      - domain/
        - models/ (Job, Worker, Lease, RetryPolicy)
        - services/ (SchedulerService, AssignmentService)

      - application/
        - usecases/ (EnrollWorker, AssignJob, AckJob, CompleteJob, FailJob, Heartbeat)

      - ports/
        - repositories/ (JobRepo, WorkerRepo, EventRepo)
        - storage/ (ArtifactStore)
        - auth/ (TokenIssuer, TokenVerifier)
        - clock/ (Clock)

      - adapters/
        - http/ (FastAPI 라우터)
        - db/ (Postgres 구현)
        - storage/ (MinIO 구현)
        - auth/ (JWT 구현)
        - observability/ (logger)

      - main.py (앱 엔트리)

    - worker/
      - **init**.py
      - domain/
        - models/ (WorkerState, JobRun)
        - services/ (WorkerLoopService, Executor)

      - application/
        - usecases/ (Enroll, Poll, Ack, Heartbeat, Execute, Report)

      - ports/
        - scheduler_api/ (SchedulerClient)
        - storage/ (ArtifactStore)
        - executor/ (CommandExecutor)
        - clock/

      - adapters/
        - http/ (SchedulerClient 구현)
        - storage/ (MinIO + DriveCache)
        - executor/ (subprocess 구현)
        - observability/

      - main.py (워커 엔트리)

  - tests/

## 구현 가이드(코드 제외, 규칙만)

- 파일 200줄 제한
- 순수 도메인(model/service)은 외부 의존 금지
- application/usecase는 ports만 의존
- adapters는 외부 라이브러리(HTTP/DB/S3) 의존 가능
- **init**.py는 공개 API를 재-export하여 외부 import 경로를 짧게 유지
- 예외 정책
  - 도메인 예외: 의미 있는 커스텀 예외
  - 어댑터 예외: 도메인 예외로 변환 후 상위로 전달

## API(개념)

### Scheduler public

- POST /workers/enroll
- POST /workers/{id}/heartbeat
- POST /jobs/poll (또는 /workers/{id}/poll)
- POST /jobs/{job_id}/ack
- POST /jobs/{job_id}/complete
- POST /jobs/{job_id}/fail

### Admin

- POST /jobs/submit
- POST /jobs/{job_id}/cancel
- GET /jobs/{job_id}
- GET /workers/{worker_id}

## 경계 케이스 필수 대응(테스트로 고정)

- 워커가 assigned 직후 죽음 → timeout 후 retrying
- 워커가 complete 보고했는데 응답 실패 → 재전송해도 멱등
- 동일 job을 두 워커에 할당 시도 → DB 트랜잭션으로 방지
- heartbeat 지연/네트워크 단절 → lease 만료로 재할당
- 실패 반복 → backoff 적용, max_retry 초과 시 failed

## 산출물(업무지시서 기준 완료 조건)

- 문서
  - 상태 머신/전이 규칙/임계값/Retry 정책 1페이지로 정리
  - Execution Contract(JobSpec) 정의 문서

- 코드 스켈레톤
  - scheduler/worker 패키지 분리 + 헥사고널 기본 뼈대
  - ports 인터페이스 정의 완료
  - Postgres 어댑터 기본 CRUD
  - HTTP 어댑터 라우팅 스텁

- 최소 동작
  - job submit → 워커 enroll/poll → execute(더미 커맨드) → complete
  - 실패 시 retrying → 재실행 → 성공/영구실패

- 테스트
  - 멱등/timeout/retry 핵심 케이스 단위 테스트

## 작업 순서(권장)

0. 레포 부트스트랩(uv, lint, test)
1. 문서: 상태 머신 + JobSpec 고정
2. domain 모델/서비스 작성
3. ports 정의
4. Postgres 스키마 + repository 어댑터
5. scheduler HTTP API
6. worker loop + executor
7. MinIO 업로드/다운로드 포트 + 어댑터
8. 통합 테스트(로컬에서 1 scheduler + 1 worker)
9. Colab 런북(노트북 템플릿) 작성: enroll→poll→run

## 추후 확장 포인트(문서에만 남기기)

- 우선순위 큐(priority)
- 리소스 프로파일(vram/label)
- 멀티 GPU 잡
- pg_cron 기반 청소 작업
- 관측 대시보드
