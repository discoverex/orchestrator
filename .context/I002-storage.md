# orchastrator storage design

## 목적

- 기존 업무지시서에 따라 구현된 orchestrator 레포에 `storage` 패키지를 추가
- 스토리지 책임을 명확히 Data Plane으로 분리
- scheduler/worker 내에 흩어져 있는 스토리지 관련 책임을 storage 계층으로 이관
- 도메인/제어 계층에서 “파일/객체 저장 구현 세부사항” 완전 제거

---

## 전제

- 기존 구조:
  - src/scheduler/\*
  - src/worker/\*

- MinIO가 SSOT
- Google Drive는 캐시/부트스트랩 보조
- Postgres는 상태/큐 전용

---

## 목표 아키텍처 (재정의)

### Plane 분리

#### 1️⃣ Control Plane

- scheduler
- 상태/할당/재시도/인증
- StoragePort에만 의존

#### 2️⃣ Compute Plane

- worker
- job 실행
- StoragePort에만 의존

#### 3️⃣ Data Plane

- storage 패키지
- MinIO 어댑터
- Drive 캐시 어댑터
- presigned URL 발급
- bucket/lifecycle 초기화

---

## 추가될 패키지 구조

```text
src/
  storage/
    __init__.py
    domain/
      models/
        object_ref.py
      services/
        storage_service.py
    ports/
      object_store.py
      cache_store.py
    adapters/
      minio_store.py
      drive_cache.py
    main.py  ## storage node entry
```

---

## 반드시 이관해야 할 책임

### 1️⃣ scheduler 내부에서 제거해야 할 것

제거 대상:

- MinIO client 직접 사용 코드
- presigned URL 생성 코드
- bucket 생성/정책 설정 코드
- 로그 파일 업로드 코드

대체 방식:

- `StoragePort` 인터페이스 호출로 대체
- scheduler는 URI 문자열만 다룸

### 2️⃣ worker 내부에서 제거해야 할 것

제거 대상:

- boto3/minio client 직접 사용
- Google Drive 직접 API 호출
- 파일 업로드/다운로드 구현 세부

대체 방식:

- `ObjectStorePort`
- `CacheStorePort`

worker는:

1. inputs_ref 전달
2. storage.download(inputs_ref, local_path)
3. 실행
4. storage.upload(local_path, outputs_ref)

구현은 storage 어댑터가 담당

---

## Storage Port 정의 (계약 고정)

### ObjectStorePort

- upload(local_path, object_uri)
- download(object_uri, local_path)
- exists(object_uri)
- generate_presigned_url(object_uri, ttl)

### CacheStorePort (선택)

- get(cache_key, local_path)
- put(cache_key, local_path)
- exists(cache_key)

---

## 경계 재설정 규칙

### 절대 규칙

- scheduler는 파일을 직접 열지 않는다
- scheduler는 로그 내용을 직접 다루지 않는다
- worker는 MinIO 클라이언트를 직접 import하지 않는다
- storage는 scheduler/worker 도메인을 import하지 않는다

의존 방향:

scheduler → storage.port
worker → storage.port
storage → 외부 라이브러리(minio, drive api)

역방향 import 금지

---

## 실행 노드 분리 방식

### 클라우드

- python -m scheduler.main

### 로컬 스토리지 노드

- python -m storage.main
- MinIO 연결/healthcheck/bucket init

### Colab 워커

- python -m worker.main

동일 레포이지만 실행 엔트리는 분리

---

## 로그 구조 재정의

### 변경 전 (문제)

- scheduler가 로그 업로드 관여

### 변경 후

- worker가 stdout/stderr 파일 생성
- worker → storage.upload
- scheduler DB에는
  - log_uri
  - run_id
  - exit_code
  - size
    만 저장

---

## Run 구조 정리

- run_id는 scheduler가 발급
- worker는 run_id 기반 prefix 사용
- 예:
  s3://bucket/jobs/{job_id}/run-{run_id}/stdout.log

retry 시:

- 새로운 run_id 발급
- 이전 run은 immutable

---

## 마이그레이션 단계

1️⃣ scheduler/worker에서 스토리지 직접 호출 코드 검색
2️⃣ storage.port 인터페이스 정의
3️⃣ 기존 구현을 adapters/minio_store로 이동
4️⃣ scheduler/worker는 port 호출로 변경
5️⃣ 테스트 통과 확인
6️⃣ import 그래프 점검 (역방향 의존 제거)

---

## 완료 조건

- scheduler/worker 코드에 minio/boto3 직접 import 없음
- 파일 경로 대신 URI 기반 인터페이스 사용
- storage 패키지 단독 실행 가능
- 로컬 MinIO 연결 테스트 통과
- 통합 테스트: job 실행 → storage 업로드 → DB에 URI 기록

---

## 향후 확장 가능성

- GCS/S3 교체 시 storage 어댑터만 변경
- 캐시 계층 제거/교체 가능
- tracking 시스템 분리 시 storage는 그대로 사용

---

## 요약

- 스토리지 책임을 Data Plane으로 완전 격리
- Control/Compute는 URI만 인지
- 레포는 하나, 실행 노드는 분리
- 장기 확장 대비한 경계 고정
