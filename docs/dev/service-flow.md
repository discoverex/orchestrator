# Service Flow

This document describes the end-to-end request and data flow across the full
orchestrator service set.

## 1) Nodes

- Prefect server node
  - Prefect API/UI
  - Prefect metadata DB
  - maintenance jobs such as flush/prune
- Worker nodes
  - fixed docker worker on `gpu-fixed`
  - optional colab workers on `gpu-colab`
- Storage node
  - worker-router
  - MinIO
  - MLflow
  - MLflow metadata DB
  - Caddy
  - cloudflared

## 2) Logical Flow

```text
operator / script
  -> Prefect API
  -> deployment run created
  -> worker polls work pool / queue
  -> worker starts flow
  -> runner resolves repo/ref or inline entrypoint
  -> runner executes engine entrypoint
  -> worker requests artifact presigns from storage-api
  -> worker uploads stdout/stderr/result/manifest
  -> engine optionally writes MLflow metadata via storage-api/mlflow
  -> Prefect marks flow terminal state
  -> flush exports completed run snapshots to storage
  -> prune removes old Prefect-local rows when configured
```

## 3) Detailed Run Path

### 3.1 Register

1. `register` container connects to Prefect API.
2. Primary deployments `e2e-job/e2e-test` and `e2e-job/e2e-test-colab` are registered by default.
3. Compatibility aliases `e2e-job/e2e-test-legacy` and `e2e-job/e2e-test-legacy-colab` may also be registered during cutover.
4. Custom flow names and deployment names are supported and can be injected during registration.
4. Deployment points to the configured flow source + entrypoint, which may still be the compatibility `run_job_flow`.

### 3.2 Submit

1. Caller submits a deployment run with `job_spec_json`.
2. Prefect stores the flow run and places it on the configured pool/queue.

### 3.3 Dispatch

1. A worker in the matching pool/queue polls Prefect.
2. Prefect hands the worker the scheduled flow run.
3. Worker spawns a local process for the flow.

### 3.4 Execute

1. Flow validates `job_spec_json`.
2. For `repo` mode, the worker resolves the requested `ref` to a fixed commit.
3. The runner prepares a temp workdir.
4. The engine entrypoint is executed with orchestrator runtime env.
5. Worker captures `stdout.log`, `stderr.log`, and `result.json`.

### 3.5 Persist Artifacts

1. Worker calls `POST /artifact/v1/presign/batch` on `storage-api`.
2. storage-api returns signed object URLs under `/objects/...`.
3. Worker uploads:
   - `stdout.log`
   - `stderr.log`
   - `result.json`
   - `artifacts.json`
4. Worker stores resulting `s3://...` URIs in the flow result payload.

### 3.6 Record MLflow Metadata

If the engine uses MLflow:

1. Engine writes to `MLFLOW_TRACKING_URI`.
2. For remote HTTP(S) MLflow with Cloudflare Access, the worker injects a local proxy.
3. worker-router proxies `/mlflow/*` to the MLflow backend.
4. In local e2e, the generated job spec injects `MLFLOW_TRACKING_PROXY_URL=http://worker-router:8200/mlflow`.
5. Engine records params/metrics/tags/status only.

### 3.7 Flush / Prune

1. Flush exports completed Prefect flow-run state snapshots to object storage.
2. Prune removes old Prefect-local rows according to retention settings.
3. Storage remains the long-term SSOT for durable run records and artifacts.

## 4) Public Endpoints

- Prefect API: `https://prefect-api.discoverex.qzz.io/api`
- storage-api machine endpoint: `https://storage-api.discoverex.qzz.io`
- storage human endpoint: `https://storage.discoverex.qzz.io`
- MLflow worker endpoint: `https://storage-api.discoverex.qzz.io/mlflow`
- MLflow UI endpoint: `https://storage.discoverex.qzz.io/mlflow`

## 5) Failure Boundaries

- Prefect-side failures
  - deployment mismatch
  - worker not polling
  - queue/pool mismatch
- Worker-side failures
  - repo checkout
  - dependency install
  - engine process exit code
  - DNS / network reachability
- Storage-side failures
  - presign failure
  - signed object path mismatch
  - object upload failure
- MLflow-side failures
  - Access policy mismatch
  - routing mismatch
  - metadata write failure

## 6) Primary Debug Order

1. Deployment registration shape
2. Worker online state and queue match
3. Flow-run state in Prefect
4. Worker logs around `run_entrypoint`, `prepare_manifest`, `upload_outputs`
5. `storage-api` `/artifact` health and signed URL shape
6. MLflow endpoint reachability and run write/readback
