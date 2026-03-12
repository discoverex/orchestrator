# Service Contracts

This document summarizes the contracts between the main services.

## 1) Prefect Deployment Contract

Deployment name:

- primary fixed: `e2e-job/e2e-test`
- primary colab: `e2e-job/e2e-test-colab`
- compatibility aliases during cutover:
  - `e2e-job/e2e-test-legacy`
  - `e2e-job/e2e-test-legacy-colab`

Current flow parameters:

- `job_spec_json`
- `resume_key`
- `checkpoint_dir`

Contract rule:

- registered deployment parameter schema must match the live flow signature

If it does not, the worker fails before engine execution with a signature mismatch.

## 2) Job Spec Contract

Canonical validator:

- [job_spec.py](/home/esillileu/discoverex/orchestrator/src/flows/job_spec.py)

Required:

- `engine`
- `entrypoint`

Required for `repo` mode:

- `repo_url`
- `ref`

Forbidden for `inline` mode:

- `repo_url`
- `ref`
- `config`

## 3) Worker Execution Contract

Canonical launcher:

- [git_runner.py](/home/esillileu/discoverex/orchestrator/src/runner/git_runner.py)

Inputs:

- validated `job_spec_json`
- Prefect flow-run metadata
- worker environment

Outputs:

- `stdout.log`
- `stderr.log`
- `result.json`
- process exit code

Behavior:

- non-interactive process execution
- temp workdir
- attempt-scoped output prefix
- optional `uv sync` in repo mode

## 4) Storage Control-Plane Contract

Canonical routes:

- `POST /artifact/v1/presign/put`
- `POST /artifact/v1/presign/get`
- `POST /artifact/v1/presign/batch`
- `POST /artifact/v1/object/head`

Canonical behavior:

- caller authenticates with Cloudflare Access headers when required
- response contains `object_uri`
- response contains signed public URL for object access

The storage control plane is request/metadata oriented. It is not the byte
transport path.

## 5) Storage Data-Plane Contract

Canonical object layout:

- `jobs/{flow_run_id}/attempt-{attempt}/stdout.log`
- `jobs/{flow_run_id}/attempt-{attempt}/stderr.log`
- `jobs/{flow_run_id}/attempt-{attempt}/result.json`
- `jobs/{flow_run_id}/attempt-{attempt}/artifacts.json`

Signed URL contract:

- storage-api returns a signed public URL under `/objects/...`
- worker uploads bytes using HTTP `PUT`
- worker does not need object-store credentials

## 6) MLflow Contract

Worker-facing URI:

- `https://storage-api.discoverex.qzz.io/mlflow`

Human UI:

- `https://storage.discoverex.qzz.io/mlflow`

Contract rules:

- workers and engines write only MLflow metadata
- artifact bytes are not uploaded through MLflow
- `s3://...` URIs may be stored as MLflow tags for linkage

## 7) Flush Contract

Producer:

- Prefect maintenance path on the Prefect node

Consumer / durable store:

- storage node object storage

Contract:

- completed flow-run state is exportable as durable JSON snapshots
- flush does not replace artifact uploads, it complements them

## 8) Prune Contract

Scope:

- Prefect-local control-plane retention only

Contract:

- prune may delete old Prefect-local flow-run state after flush
- prune must not be treated as artifact deletion
- storage remains the durable artifact and exported-state authority

## 9) Standard Validation Contract

Standard smoke tools:

- [prefect_fixed_dummy_smoke.py](/home/esillileu/discoverex/orchestrator/scripts/observability/prefect_fixed_dummy_smoke.py)
- [prefect_verify_standard_dummy_run.py](/home/esillileu/discoverex/orchestrator/scripts/observability/prefect_verify_standard_dummy_run.py)

Expected outcome:

1. flow run reaches `COMPLETED`
2. artifact objects exist
3. MLflow run exists
4. MLflow tags point back to the flow run
