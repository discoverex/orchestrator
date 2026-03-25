# Service Flow

이 문서는 시스템 전체의 개념적 실행 흐름만 설명한다. 배포 이름, 세부 API shape,
운영 절차는 각각 계약 문서와 가이드를 따른다.

## 1) 참여 노드

- Prefect node: deployment registration, scheduling, state 관리
- Worker node: flow 실행, repo checkout, entrypoint 실행
- Storage node: presign/head 제어면, object persistence, MLflow routing

## 2) End-to-End Flow

```text
operator / automation
  -> Prefect deployment run 생성
  -> worker가 pool/queue에서 run 수신
  -> flow가 job_spec_json 검증
  -> runner가 repo 또는 inline entrypoint 실행
  -> worker가 stdout/stderr/result 및 engine artifact를 정리
  -> storage-api가 presigned URL 발급
  -> worker가 object 업로드
  -> engine이 필요하면 MLFLOW_TRACKING_URI로 metadata 기록
  -> Prefect가 terminal state 기록
  -> maintenance가 completed run snapshot을 flush/prune
```

## 3) 단계별 책임

### Register

- 등록 주체는 `register` container 또는 관련 CLI다.
- 기본 worker-runtime entrypoint는 `src/flows/worker_runtime/flow.py:run_worker_job_flow`다.
- canonical deployment naming과 compat alias는 [deployments/e2e/README.md](../../deployments/e2e/README.md)에서만 정의한다.

### Execute

- flow는 `job_spec_json`을 검증한다.
- `repo` mode에서는 `ref`를 먼저 고정 commit으로 resolve한다.
- runner는 임시 workdir에서 engine entrypoint를 실행한다.
- worker는 `stdout.log`, `stderr.log`, `result.json`을 항상 수집한다.

### Persist

- worker는 storage control-plane에 presign 요청을 보낸다.
- 반환된 signed URL을 사용해 object를 업로드한다.
- engine이 `ORCH_ENGINE_ARTIFACT_DIR`와 manifest를 사용하면 worker가 추가 artifact도 업로드한다.

### Observe

- engine은 `MLFLOW_TRACKING_URI`만 사용한다.
- 원격 HTTP(S) MLflow와 Cloudflare Access 조합에서는 worker가 local proxy를 둘 수 있다.
- completed run snapshot export와 retention은 Prefect maintenance 경로가 담당한다.

## 4) 실패 경계

- Prefect: deployment mismatch, queue/pool mismatch, worker polling 부재
- Worker: repo checkout 실패, dependency 준비 실패, engine exit code 비정상
- Storage: presign 실패, signed URL mismatch, upload 실패
- MLflow: 접근 정책 mismatch, routing 실패, metadata write 실패

## 5) 다음 문서

- 인증 경계: [auth-model.md](auth-model.md)
- 실행 계약: [../contracts/execution.md](../contracts/execution.md)
- 서비스 인터페이스: [../contracts/service-interface.md](../contracts/service-interface.md)
- 운영 절차: [../guides/setup-prefect.md](../guides/setup-prefect.md), [../guides/setup-storage.md](../guides/setup-storage.md)
