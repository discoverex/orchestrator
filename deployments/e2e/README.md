# E2E Deployment Spec

이 디렉터리는 canonical E2E deployment naming의 source of truth다.
운영 절차, 인증, runtime env는 다른 문서로 분리한다.

## Canonical Defaults

- flow entrypoint: `src/flows/worker_runtime/flow.py:run_worker_job_flow`
- flow name: `e2e-job`
- fixed deployment: `e2e-job/e2e-test`
- colab deployment: `e2e-job/e2e-test-colab`

## Compatibility Aliases

현재 코드와 등록 설정에는 아래 alias가 남아 있다.

- `e2e-job/e2e-test-legacy`
- `e2e-job/e2e-test-colab-legacy`

세부 정의와 queue 정보는 [e2e-deployments.yaml](e2e-deployments.yaml)을 따른다.

## Scope

- 이 문서는 flow/deployment naming과 compat alias만 다룬다.
- `PREFECT_API_URL`, auth headers, source root, storage endpoint 같은 runtime 설정은 포함하지 않는다.
