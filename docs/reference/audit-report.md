# CLI Audit Report

이 문서는 `bin/cli`에서 제공하는 전체 인터페이스 및 기능을 점검한 결과 보고서입니다. `cli.md`를 기준으로 작성되었습니다.

## 1. CLI 점검 요약

*   **점검 대상**: `bin/cli`의 10개 도메인 및 하위 액션
*   **제외 범위**: 서비스 기동/정지(`up`/`down`) 및 E2E 테스트(`e2e`) 명령 (실행 없이 상태만 확인)
*   **점검 결과**: 모든 도메인의 엔트리포인트(`scripts/<domain>/cli.sh`)와 부트스트랩 환경이 정상적으로 구성되어 있음을 확인했습니다.

## 2. CLI 기능 상태 표

다음 표는 각 명령의 유형과 상태를 나타냅니다.

| Domain | Action | Type | Side Effect | Status (Audit) |
| :--- | :--- | :--- | :--- | :--- |
| **base** | `build` | Modification | Docker 이미지 생성 (`orchestrator-base:local`) | Execution Skipped |
| **runtime** | `init` | Modification | `${RUNTIME_ROOT}` 하위 디렉토리 생성 | Execution Skipped |
| **storage** | `up` / `down` | Service | 컨테이너 라이프사이클 관리 | Out of Scope |
| | `ps` / `logs` | Read-only | 컨테이너 상태/로그 조회 | **OK** |
| | `build` | Modification | Docker 이미지 빌드 | Execution Skipped |
| **local** | `up` / `down` | Service | 컨테이너 라이프사이클 관리 | Out of Scope |
| | `ps` / `logs` | Read-only | 컨테이너 상태/로그 조회 | **OK** |
| | `build` | Modification | Docker 이미지 빌드 | Execution Skipped |
| **register** | `run` | Modification | 배포 등록 컨테이너 실행 | Execution Skipped |
| | `build` | Modification | Docker 이미지 빌드 | Execution Skipped |
| **worker** | `fixed <up/down>` | Service | Fixed Worker 컨테이너 관리 | Out of Scope |
| | `fixed <ps/logs/build>` | Mixed | 컨테이너 조회 및 빌드 | **OK** (ReadOnly 우선) |
| | `register-gpu` | Modification | GPU 배포 등록 실행 | Execution Skipped |
| | `submit` | Modification | Prefect Flow Run 생성 | Execution Skipped |
| **observability**| `workers` | Read-only | Prefect Worker 목록 조회 | **OK** |
| | `fixed-dummy-smoke`| Modification | Smoke 테스트용 Flow Run 생성 | Execution Skipped |
| **prefect** | `up` / `down` | Service | Prefect Server 컨테이너 관리 | Out of Scope |
| | `ps` / `logs` | Read-only | 컨테이너 상태/로그 조회 | **OK** |
| | `flush` / `prune` | Modification | 완료된 Flow 데이터 정리 | Execution Skipped |
| | `install --remote` | Modification | 원격지 VM 환경 부트스트랩 | Execution Skipped |
| **e2e** | `local` / `remote` | E2E | 전체 스택 테스트 실행 | Out of Scope |
| **ops** | `connect` | Read-only | 원격지 SSH 접속 | **OK** (환경 변수 필요) |
| | `postgres` | Read-only | 원격지 DB 쉘 접속 | **OK** (환경 변수 필요) |
| | `dump` | Modification | 원격지 DB 덤프 생성 (로컬 파일 저장) | Execution Skipped |
| | `ci` | Modification | 코드 린트/포맷 보정 및 테스트 | Execution Skipped |

> **참고**: `Modification` 유형은 파일 시스템 변경, Docker 이미지 생성, DB 데이터 변경, 혹은 원격 서버 상태 변경을 유발하는 명령입니다.

## 3. 오류 발생 키워드 및 해결 방법

점검 과정에서 식별된 잠재적 오류 키워드와 원인, 해결 방법입니다.

### A. 환경 변수 누락 (Remote 관련)
*   **오류 키워드**: `REMOTE_USERNAME is required`, `REMOTE_HOST is required`, `GITHUB_DEPLOY_KEY_PATH is required`
*   **원인**: 원격 명령(`--remote` 또는 `ops` 도메인) 실행 시 필수 환경 변수가 로컬 `.env` 파일에 정의되지 않았거나 `load_repo_env`가 실패함.
*   **해결 방법**:
    1.  `.env.example` 파일을 복사하여 `.env`를 생성합니다.
    2.  `REMOTE_USERNAME`, `REMOTE_HOST`, `GITHUB_DEPLOY_KEY_PATH` 항목을 실제 서버 정보에 맞게 수정합니다.

### B. SSH 접속 실패
*   **오류 키워드**: `Permission denied (publickey)`, `Identity file ... not accessible`
*   **원인**: SSH 키 경로가 잘못되었거나, 키 파일의 권한이 너무 개방적임(600 권한 필요).
*   **해결 방법**: 
    1.  `GITHUB_DEPLOY_KEY_PATH`가 올바른 경로인지 확인합니다.
    2.  `chmod 600 <key_file>` 명령을 통해 권한을 수정합니다.

### C. Docker/Compose 환경 오류
*   **오류 키워드**: `docker-compose: command not found`, `Cannot connect to the Docker daemon`
*   **원인**: Docker 엔진이 설치되지 않았거나 실행 중이지 않음. 혹은 `docker-compose` v1/v2 혼용 문제.
*   **해결 방법**:
    1.  `docker version` 명령으로 데몬 상태를 확인합니다.
    2.  이 프로젝트는 `docker compose` (v2)를 기본으로 사용하므로 최신 Docker Desktop 또는 Docker Engine을 설치합니다.

### D. 런타임 디렉토리 권한 및 자동 초기화
*   **오류 키워드**: `Permission denied`, `mkdir: cannot create directory`
*   **원인**: `worker up` 실행 시 런타임 디렉토리가 없거나, 호스트 디렉토리의 권한이 컨테이너 내부 유저(UID 10001)와 맞지 않음.
*   **해결 방법 (조치 완료)**:
    1.  `bin/cli worker fixed up` 실행 시 `runtime init worker`를 자동으로 호출하도록 수정했습니다.
    2.  체크포인트 디렉토리에 대해 `sudo chown -R 10001:10001`을 수행하여 권한 문제를 사전에 방지하도록 로직을 강화했습니다.
    3.  `docker-compose.yml`의 볼륨 마운트 경로를 표준 런타임 구조(`../../../../runtime/worker/checkpoints`)로 일치시켰습니다.

### F. 원격 E2E 스토리지 연동
*   **오류 키워드**: `minio_health failed`, `presign url with localhost`
*   **원인**: 원격 E2E 테스트가 로컬 MinIO(127.0.0.1:9000)가 떠 있는 것을 전제로 동작하거나, 업로드용 Presigned URL이 내부 도메인으로 생성됨.
*   **해결 방법 (조치 완료)**:
    1.  `e2e remote`에서 로컬 MinIO 헬스체크를 제거하고, 공개 도메인(`STORAGE_API_URL`)에 대해 Cloudflare Access 인증 헤더를 포함한 헬스체크를 수행하도록 수정했습니다.
    2.  `storage` 서비스에서 `internal_presign_base_url`이 없을 경우 `public_base_url`을 사용하도록 수정하여, 외부 워커가 공개 도메인을 통해 아티팩트를 업로드할 수 있도록 개선했습니다.

### E. Python 의존성 및 uv 도구
*   **오류 키워드**: `uvx: command not found`, `ModuleNotFoundError`
*   **원인**: `ops ci` 등에서 사용하는 `uv` 도구가 설치되지 않았거나 가상환경이 동기화되지 않음.
*   **해결 방법**:
    1.  `curl -LsSf https://astral.sh/uv/install.sh | sh`를 통해 `uv`를 설치합니다.
    2.  `uv sync`를 실행하여 의존성을 설치합니다.
