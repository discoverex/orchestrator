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

## Local Explorer APIs

Local-only operator explorer (disabled by default):

- `POST /v1/explorer/session`
- `DELETE /v1/explorer/session`
- `GET /v1/explorer/buckets`
- `GET /v1/explorer/objects`
- `GET /v1/explorer/download`
- `GET /explorer`

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
