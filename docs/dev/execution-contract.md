# Execution Contract (Prefect)

## Flow Input

- `repo_url: str`
- `ref: str` (branch/tag/sha)
- `entrypoint: list[str]`
- `inputs_ref: list[str]` (optional)
- `env: dict[str, str]` (optional)
- `outputs_prefix: str | None` (optional)

## Version Pinning Policy

- Flow starts with `resolve_commit(ref)`.
- If `ref` is branch/tag, it is resolved once to `resolved_commit`.
- All retries use the same `resolved_commit`.

## Artifact Layout

- `jobs/{flow_run_id}/attempt-{attempt}/stdout.log`
- `jobs/{flow_run_id}/attempt-{attempt}/stderr.log`
- `jobs/{flow_run_id}/attempt-{attempt}/result.json`
- `jobs/{flow_run_id}/attempt-{attempt}/artifacts.json`

## Storage Gateway APIs

- `POST /v1/presign/put`
- `POST /v1/presign/get`
- `POST /v1/presign/batch`
- `POST /v1/object/head`
- `PUT /v1/object/proxy?token=...`
- `GET /v1/object/proxy?token=...`

All endpoints require bearer auth:

- `Authorization: Bearer <STORAGE_GATEWAY_TOKEN>`

Optional additional gateway protection:

- Cloudflare Access service-token headers:
  - `CF-Access-Client-Id`
  - `CF-Access-Client-Secret`

## Flow Result Metadata

- `flow_run_id`
- `attempt`
- `resolved_commit`
- `outputs_prefix`
- `stdout_uri`
- `stderr_uri`
- `result_uri`
- `manifest_uri`
- `exit_code`

`Prefect flow result` is the source of truth for run metadata.

## E2E Acceptance (Register -> Worker -> Storage)

The deterministic script `scripts/e2e/e2e_local_orchestrator.sh` verifies the full orchestration chain in three modes:

- `core`: deployment register, worker execution, object persistence in MinIO
- `mlflow`: `core` + MLflow run tag linkage (`artifact_*_uri`)
- `full`: `mlflow` + external domain/Cloudflare Access path checks

`full` mode includes prereq gating before MLflow tag checks:

1. required env keys exist (`MLFLOW_TRACKING_URI`, `MLFLOW_PUBLIC_URL`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`)
2. DNS resolves for tracking/public MLflow hostnames

Core pass criteria:

1. `engine-run/engine-run` deployment exists after register.
2. Submitted flow run reaches `COMPLETED`.
3. All required objects exist:
   - `stdout.log`
   - `stderr.log`
   - `result.json`
   - `artifacts.json`
4. `artifacts.json` metadata matches expected `flow_run_id`, `attempt`, and object URIs.
