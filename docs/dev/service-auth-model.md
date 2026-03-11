# Service Auth Model

This document describes how authentication is split across the main service
boundaries.

## 1) Principle

Use public machine endpoints with scoped credentials.

- Workers and automation should carry only public-facing credentials.
- Backend service credentials stay on the node that owns the backend.
- MinIO root credentials must not be distributed to workers.
- MLflow DB credentials must not be distributed to workers.

## 2) Trust Zones

### External Clients

- operator scripts
- register container
- observability scripts
- workers

These clients may hold:

- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`
- public service URLs

### Internal Backend Services

- MinIO
- MLflow backend
- MLflow DB
- worker-router internals

These services may hold:

- MinIO access key / secret
- MLflow DB credentials
- backend-only internal hostnames

## 3) Prefect Auth

Public endpoint:

- `PREFECT_API_URL=https://prefect-api.discoverex.qzz.io/api`

Client-side auth model:

- if Prefect is behind Cloudflare Access, clients send:
  - `CF-Access-Client-Id`
  - `CF-Access-Client-Secret`
- worker and register entrypoints convert these into Prefect client custom headers when needed

Used by:

- register stack
- workers
- observability scripts
- remote e2e scripts

## 4) Storage Auth

Public machine endpoint:

- `STORAGE_API_URL=https://storage-api.discoverex.qzz.io`

Worker/API auth model:

- workers call `/artifact/...` using Cloudflare Access service-token headers
- worker-router enforces request auth when `GATEWAY_REQUIRE_CF_ACCESS=true`

Artifact byte upload model:

1. Worker authenticates to `/artifact/v1/presign/...`
2. storage-api issues signed object URLs
3. Worker uploads bytes to the signed `/objects/...` URL

Important:

- the worker authenticates to storage-api control-plane routes
- the worker does not need MinIO credentials
- signed object URLs are the data-plane contract

## 5) MLflow Auth

Worker-facing tracking URI:

- `MLFLOW_TRACKING_URI=https://storage-api.discoverex.qzz.io/mlflow`

Human UI:

- `https://storage.discoverex.qzz.io/mlflow`

Auth model:

- public worker traffic enters via Cloudflare Access
- worker uses the same service token pair it already carries
- if the engine writes to remote MLflow over HTTP(S), the worker may start a local MLflow proxy that injects the Access headers

The engine should not know backend MLflow container addresses or DB credentials.

## 6) Human UI Auth

Human endpoints are expected to be protected separately from machine endpoints.

- `storage.discoverex.qzz.io`
  - MLflow UI
  - MinIO console
  - pgAdmin
- `storage-api.discoverex.qzz.io`
  - machine API and signed object paths

Recommended split:

- human domain protected by Cloudflare Access identity policy
- machine domain protected by service-token policy

## 7) Secret Distribution Rules

Workers may hold:

- `PREFECT_API_URL`
- `STORAGE_API_URL`
- `MLFLOW_TRACKING_URI`
- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`

Workers must not hold:

- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `MLFLOW_DB_PASSWORD`
- internal-only backend URLs as a required runtime dependency

Storage node may hold:

- MinIO credentials
- MLflow DB credentials
- internal backend hostnames

## 8) Common Misconfiguration Patterns

- Prefect deployment can be reached, but storage-api DNS is missing
- Cloudflare tunnel route exists for human host but not machine host
- `MINIO_PUBLIC_BASE_URL` points to the wrong public path
- MLflow tracking URI points to a stale host
- register stack misses Prefect custom headers and silently registers against the wrong auth context

## 9) Quick Verification

Prefect:

```bash
uv run python scripts/observability/prefect_check_auth.py
```

Storage + MLflow:

```bash
./bin/cli observability fixed-dummy-smoke --deployment-name discoverex-engine-run --timeout-sec 240
uv run python scripts/observability/prefect_verify_standard_dummy_run.py --flow-run-id <FLOW_RUN_ID>
```
