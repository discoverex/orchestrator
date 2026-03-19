# Engine Handover

이 문서는 엔진 레포 개발자가 현재 오케스트레이터 worker 위에서 엔진을 직접 실행 가능하게 만들기 위한 handover다.

전제:

- 오케스트레이터는 이제 `worker platform`만 관리한다.
- 엔진 레포가 직접 Prefect deployment를 정의하고 등록한다.
- 엔진 레포가 clone, branch checkout, `uv sync`, 실제 엔진 실행을 직접 소유한다.
- 오케스트레이터는 worker 안에서 공용 마운트 경로와 로컬 프록시, staged artifact 자동 업로드만 제공한다.

## 1. 최종 역할 분리

오케스트레이터가 하는 일:

- Prefect worker 실행
- work pool / work queue polling
- worker-local Prefect proxy 제공
- worker-local MLflow proxy 제공
- worker-local artifact service 제공
- 공용 마운트 루트 제공
- staged artifact 디렉터리 자동 업로드

엔진 레포가 해야 하는 일:

- 자기 Prefect flow 정의
- 자기 Prefect deployment 등록
- 필요한 repo clone / branch checkout
- `uv sync`
- 엔진 실행
- 산출물 파일을 공용 staging 디렉터리에 작성
- 완료 마커 생성

중요:

- 엔진은 더 이상 오케스트레이터 runner flow를 호출하지 않는다.
- 엔진은 더 이상 오케스트레이터의 register CLI에 의존하지 않는다.
- 엔진은 자기 deployment를 직접 등록해야 한다.

## 2. Worker가 보장하는 런타임 계약

worker 안에서 엔진이 신뢰해도 되는 env:

- `ORCH_WORKER_RUNTIME_DIR`
- `ORCH_CACHE_DIR`
- `PREFECT_API_URL`
- `MLFLOW_TRACKING_URI`
- `STORAGE_API_URL`
- `ORCH_REMOTE_PREFECT_API_URL`
- `ORCH_REMOTE_MLFLOW_TRACKING_URI`

의미:

- `ORCH_WORKER_RUNTIME_DIR`
  공용 writable runtime mount root
  기본값: `/var/lib/orchestrator`

- `ORCH_CACHE_DIR`
  공용 cache root
  기본값: `/var/lib/orchestrator/cache`

- `PREFECT_API_URL`
  worker-local Prefect proxy URL
  형식: `http://127.0.0.1:8200/prefect/api`

- `MLFLOW_TRACKING_URI`
  worker-local MLflow proxy URL
  형식: `http://127.0.0.1:8200/mlflow`

- `STORAGE_API_URL`
  worker-local artifact service base URL
  형식: `http://127.0.0.1:8200/artifact`

- `ORCH_REMOTE_PREFECT_API_URL`
  원격 Prefect API 원본 URL

- `ORCH_REMOTE_MLFLOW_TRACKING_URI`
  원격 MLflow 원본 URL

엔진이 기대하면 안 되는 것:

- `ORCH_ENGINE_ARTIFACT_DIR`
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- `ORCH_JOB_INPUTS_JSON`
- `ORCH_JOB_NAME`
- `ORCH_JOB_CONFIG_PATH`
- `ORCHESTRATOR_CHECKPOINT_DIR`
- 내부 repo cache / model cache 하위 경로

즉 엔진은 worker가 “세부 실행용 env를 주입해준다”고 가정하면 안 된다.  
엔진은 mount root와 local proxy URL만 사용해야 한다.

## 3. 엔진 flow 구현 방식

엔진 레포는 자기 `@flow`를 직접 정의한다.

권장 흐름:

1. Prefect flow 시작
2. 현재 flow run id 확보
3. 필요한 repo clone 또는 branch checkout
4. 작업 디렉터리에서 `uv sync`
5. 실제 엔진 로직 실행
6. 결과 파일을 staging 디렉터리에 작성
7. `_UPLOAD_READY` 생성
8. flow 종료

핵심 원칙:

- 엔진 flow가 최상위 실행 단위다.
- 오케스트레이터 flow를 다시 감싸지 않는다.
- `PREFECT_API_URL`은 이미 worker-local proxy를 가리키므로 엔진은 별도 인증 헤더를 몰라도 된다.
- `MLFLOW_TRACKING_URI`도 이미 worker-local proxy를 가리키므로 엔진은 CF Access 자격을 몰라도 된다.

## 4. Prefect deployment 구현 요구사항

엔진 레포가 직접 해야 하는 것:

- `prefect.yaml` 또는 엔진 자체 배포 스크립트 작성
- flow entrypoint를 엔진 레포 내부 callable로 지정
- 실행 대상 work pool / queue 지정
- 엔진 파라미터 스키마 직접 정의

운영 모델:

- deployment source는 엔진 레포가 소유한다.
- 어떤 브랜치/태그/소스를 실행할지 엔진 쪽 배포 전략으로 결정한다.
- 오케스트레이터는 deployment를 대신 등록하지 않는다.

주의:

- 엔진이 매 실행마다 다른 branch를 checkout해야 한다면, 그 로직도 엔진 flow 내부에 직접 구현해야 한다.
- 현재 구조에서는 “부모 runner가 branch 준비를 대신 해준다”는 모델이 없다.

## 5. `uv sync` 규칙

엔진은 자기 작업 디렉터리에서 직접 `uv sync`를 수행해야 한다.

현재 권장:

- `--frozen` 없이 실행
- 즉 단순히 `uv sync`

이유:

- 오케스트레이터 쪽 기본 정책도 frozen 없이 가는 방향으로 맞췄다.
- lock mismatch 때문에 배포가 막히는 것보다, 엔진 레포가 자기 환경을 스스로 맞추는 쪽이 우선이다.

## 6. 아티팩트 업로드 계약

이제 엔진은 worker API를 직접 호출할 필요가 없다.  
기본 경로는 `staging directory + ready marker`다.

### 6.1 staging root

엔진은 아래 디렉터리를 사용한다.

```bash
${ORCH_WORKER_RUNTIME_DIR}/engine-artifacts/<prefect-flow-run-id>/
```

예:

```bash
/var/lib/orchestrator/engine-artifacts/6f3f2d2e-.../
```

여기 `<prefect-flow-run-id>`는 실제 Prefect flow run id를 쓰는 것을 권장한다.

### 6.2 엔진이 해야 하는 일

예를 들어 아래처럼 파일을 쓴다.

```text
${ORCH_WORKER_RUNTIME_DIR}/engine-artifacts/<flow-run-id>/scene/scene.json
${ORCH_WORKER_RUNTIME_DIR}/engine-artifacts/<flow-run-id>/scene/verification.json
${ORCH_WORKER_RUNTIME_DIR}/engine-artifacts/<flow-run-id>/logs/run.log
```

그리고 모든 쓰기가 끝나면 아래 파일을 생성한다.

```text
${ORCH_WORKER_RUNTIME_DIR}/engine-artifacts/<flow-run-id>/_UPLOAD_READY
```

빈 파일이면 충분하다.

### 6.3 worker가 자동으로 하는 일

worker-side uploader가 주기적으로 아래를 스캔한다.

```text
${ORCH_WORKER_RUNTIME_DIR}/engine-artifacts/*
```

`_UPLOAD_READY`가 있고 `.uploaded.json`이 없으면:

- staging 디렉터리 아래 파일들을 업로드
- 업로드 object key를 `engine/<relative_path>` 기준으로 생성
- `engine-artifacts.json` manifest도 worker가 생성해서 업로드
- 로컬에 `.uploaded.json` 상태 파일 기록

현재 uploader 기준 상수:

- staging dir name: `engine-artifacts`
- ready marker: `_UPLOAD_READY`
- uploaded marker: `.uploaded.json`
- generated manifest name: `engine-artifacts.json`

중요:

- 엔진은 manifest를 직접 만들 필요가 없다.
- 엔진은 업로드 API, presign, MinIO 세부 동작을 몰라도 된다.

### 6.4 현재 제한

현재 uploader는 업로드 경로를 다음처럼 고정한다.

- flow run id: staging 디렉터리 이름
- attempt: `1`

즉 retry/attempt를 정교하게 반영하는 계약은 아직 없다.  
당장은 `<flow-run-id>` 단위 durable artifact 수집만 보장된다고 보면 된다.

## 7. MLflow 사용 방법

엔진은 `MLFLOW_TRACKING_URI`만 사용하면 된다.

현재 worker가 이미:

- 원격 MLflow URL 보유
- 필요한 인증 보유
- local proxy 제공

를 처리한다.

따라서 엔진은 그냥 일반 MLflow client를 써도 된다.

권장:

- 원격 URL 대신 항상 `MLFLOW_TRACKING_URI` env를 읽는다.
- CF Access token이나 별도 헤더를 직접 다루지 않는다.

## 8. Prefect API 사용 방법

엔진은 `PREFECT_API_URL`만 사용하면 된다.

현재 worker가 이미:

- 원격 Prefect API 원본 URL 보유
- Prefect custom headers / Cloudflare Access 인증 보유
- local proxy 제공

를 처리한다.

따라서 엔진은:

- 자기 deployment 등록 시 일반적인 Prefect client / CLI 사용
- 실행 중 Prefect flow run 추적은 기존 방식 그대로 사용

만 하면 된다.

별도 인증 헤더를 엔진 코드에 넣지 말 것.

## 9. 엔진에서 바로 구현해야 하는 최소 코드

엔진 flow에서 최소로 필요한 로직:

1. Prefect flow run id 읽기
2. `ORCH_WORKER_RUNTIME_DIR` 아래 staging dir 계산
3. 출력 파일 쓰기
4. `_UPLOAD_READY` 생성

예시 개념:

```python
from pathlib import Path
import os
from prefect import flow
from prefect.runtime import flow_run


@flow
def engine_flow() -> None:
    run_id = flow_run.get_id()
    runtime_root = Path(os.environ["ORCH_WORKER_RUNTIME_DIR"])
    out_dir = runtime_root / "engine-artifacts" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    scene_dir = out_dir / "scene"
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / "scene.json").write_text('{"ok": true}', encoding="utf-8")

    (out_dir / "_UPLOAD_READY").write_text("", encoding="utf-8")
```

여기에 엔진 고유 clone / `uv sync` / 실행 로직을 추가하면 된다.

## 10. 엔진 레포 체크리스트

엔진 개발자는 아래를 완료하면 된다.

### 필수

- 엔진 Prefect flow 정의
- 엔진 deployment 직접 등록
- flow 내부에서 clone / branch checkout 구현
- flow 내부에서 `uv sync` 구현
- `ORCH_WORKER_RUNTIME_DIR` 기반 artifact staging 구현
- `_UPLOAD_READY` 생성 구현
- `PREFECT_API_URL` / `MLFLOW_TRACKING_URI` env 사용

### 하지 말아야 할 것

- 오케스트레이터 runner flow 호출
- 오케스트레이터 register CLI 의존
- CF Access 자격을 엔진 코드에서 직접 사용
- MinIO presign / PUT 로직 직접 구현
- worker 내부 세부 경로에 의존

## 11. 현재 남아 있는 보조 경로

오케스트레이터 레포에는 직접 업로드용 helper도 남아 있다.

- [src/engine_support/artifacts.py](src/engine_support/artifacts.py)

하지만 기본 권장 경로는 아니다.  
기본값은 `staging + _UPLOAD_READY + worker auto-upload`다.

즉 엔진 개발자는 이 helper를 몰라도 된다.

## 12. 운영자가 알아야 할 점

- worker는 현재 startup 시 background uploader를 같이 띄운다.
- uploader는 `WORKER_ARTIFACT_SWEEP_INTERVAL_SEC` 간격으로 scan 한다.
- 현재 기본 scan interval은 `5`초다.
- worker runtime mount가 유지되는 한 staged artifact는 worker가 수집 가능하다.

## 13. 변경 후 기대되는 개발 경험

엔진 개발자는 이제 이 오케스트레이터 레포의 실행 세부를 거의 몰라도 된다.

알아야 하는 것은 사실상 아래뿐이다.

- 어떤 env를 읽을 수 있는지
- 산출물을 어디에 쓰는지
- 완료 마커 이름이 무엇인지
- deployment를 엔진 레포에서 직접 등록해야 한다는 점

즉 handover 관점의 핵심 문장은 이거다:

`엔진은 자기 flow와 deployment를 직접 소유하고, worker는 mount root와 local proxy와 auto-upload만 제공한다.`
