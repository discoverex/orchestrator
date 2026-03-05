# Next Plan: 컨테이너 격리 E2E 안정화 + Cloudflare DNS 최종 수렴

## 0) 현재 결론 (2026-03-05 기준)

- `core` E2E는 통과한다.
  - 스케줄러(Prefect) -> 워커 -> storage-gateway -> MinIO 흐름 정상
  - 아티팩트(stdout/stderr/result/manifest) 검증 정상
- `full` E2E는 현재 실패한다.
  - 실패 지점: `verify-mlflow-tags`
  - 현재 원인: MLflow write API(`runs/create`)가 `HTTP 403`으로 차단됨
  - DNS 해석 실패 이슈는 해소됨(`verify-full-prereqs` 통과 확인)
- `cloudflared` 터널 프로세스 자체는 정상 등록됨(Registered tunnel connection 확인).

## 1) 내가 하려고 했던 것 (진행 의도)

1. 로컬/호스트 `.venv` 간섭 제거
- 모든 노드를 이미지 기반으로 실행하여 프로젝트 로컬 가상환경과 분리

2. E2E를 실제 컴포즈 기반으로 고정
- mock이 아니라 실제 `docker compose` 스택 기동 후 E2E 검증

3. Cloudflare 포함 full 경로 검증
- 터널 + 외부 도메인 + CF Access 헤더까지 포함해 end-to-end 확인

## 2) 이미 반영된 핵심 변경

1. 이미지 기반 런타임 구성
- `infra/images/base.Dockerfile` (공통 의존성 베이스)
- `infra/images/storage-gateway.Dockerfile`
- `infra/images/worker.Dockerfile`
- `infra/images/register.Dockerfile`
- `.dockerignore`

2. 컴포즈 전환
- `docker-compose.local.yml`: storage-gateway/worker/register 이미지 기반 실행
- `infra/stacks/storage-node/docker-compose.yml`: storage-gateway 이미지 기반 실행

3. MLflow 기동 안정화 보강
- `infra/images/mlflow.Dockerfile` 추가 (`psycopg2-binary` 포함)
- `infra/stacks/storage-node/docker-compose.yml`의 `mlflow`를 위 이미지로 변경
- `mlflow` healthcheck를 `curl` -> `python urllib`로 변경

4. E2E 오케스트레이터 개선
- `scripts/e2e/e2e_orchestrator.sh`를 컨테이너 기반 실행으로 정렬
- `core/mlflow/full` 모드와 결과 요약(`artifacts/e2e/.../summary.json`) 유지

## 3) 지금부터 해야 할 일 (우선순위)

1. Cloudflare Access 정책 최종 점검 (최우선, 미완료)
- `mlflow` write API (`/api/2.0/mlflow/runs/create`, `/runs/set-tag`) 허용 여부 확인
- Service Token이 read-only 정책에 묶여 있지 않은지 확인

2. Cloudflare DNS 레코드 재확인 (보조, 진행중)
- `mlflow.discoverex.qzz.io` 레코드가 실제로 조회 가능해야 함
- 권장: CNAME -> `<tunnel-id>.cfargotunnel.com` (proxied)

3. CF Access 앱/토큰 재검증 (미완료)
- `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET`가 해당 앱 정책에 매칭되는지 확인

4. full E2E 재실행 (미완료)
- Access 정책 수정 후 `verify-mlflow-tags`와 외부 접근 단계까지 통과 여부 재확인

5. 문서/운영 체크리스트 확정 (진행중)
- `.env` 필수키와 실행 순서를 README/ops 문서에 최종 고정
- `scripts/e2e/e2e_orchestrator.sh`에 `full` 모드 사전검증(`verify-full-prereqs`) 추가
- `scripts/e2e/e2e_orchestrator.sh`에 `verify-mlflow-tracking-access` 추가

## 4) 실행 방법 (상세)

### 4.1 사전 환경변수 (`.env`)

필수:

```env
MLFLOW_TRACKING_URI=https://mlflow.discoverex.qzz.io
MLFLOW_PUBLIC_URL=https://mlflow.discoverex.qzz.io
CF_ACCESS_CLIENT_ID=<cloudflare-access-client-id>
CF_ACCESS_CLIENT_SECRET=<cloudflare-access-client-secret>
```

권장 확인:

```bash
rg -n '^(MLFLOW_TRACKING_URI|MLFLOW_PUBLIC_URL|CF_ACCESS_CLIENT_ID|CF_ACCESS_CLIENT_SECRET)=' .env
```

### 4.2 스토리지/터널 스택 기동

```bash
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml up -d --build
```

상태 확인:

```bash
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml ps
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml logs cloudflared --tail=80
```

### 4.3 DNS/접속 확인

로컬 DNS 해석:

```bash
getent ahosts mlflow.discoverex.qzz.io
```

Access 토큰 포함 접속 확인:

```bash
set -a; source .env; set +a
curl -svI https://mlflow.discoverex.qzz.io \
  -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}"
```

### 4.4 E2E 실행

코어 경로:

```bash
scripts/e2e/e2e_orchestrator.sh --mode core
```

전체 경로:

```bash
scripts/e2e/e2e_orchestrator.sh --mode full
```

결과 확인:

```bash
latest=$(ls -1dt artifacts/e2e/* | head -n1)
cat "$latest/summary.json"
```

## 5) 성공 기준

- `core`: 항상 PASS (현재 달성)
- `full`: 아래 모두 PASS
  - flow completion
  - storage object verification
  - mlflow tag verification
  - external access check (CF headers)

## 6) 실패 시 빠른 판별표

1. `missing required env: MLFLOW_TRACKING_URI`
- `.env`에 키 누락

2. `verify-full-prereqs` 실패
- `.env` 누락 또는 DNS 레코드/전파 문제

3. `mlflow runs/create failed: HTTP 403`
- CF Access 정책에서 write API가 차단되었거나 토큰 권한이 부족

4. `mlflow` unhealthy
- `infra/stacks/storage-node/docker-compose.yml`의 `mlflow` 이미지/healthcheck 설정 확인
