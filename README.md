# orchestrator

Prefect-based orchestration workspace with four responsibilities:

- `flows`: compatibility and maintenance Prefect workflows
- `runner`: execution adapter for source checkout + entrypoint execution
- `storage`: hexagonal storage module for presign/head control-plane logic
- `worker_router`: worker-facing auth gateway for storage control APIs and MLflow

## Docs

Design and contracts:

- `docs/dev/service-flow.md`
- `docs/dev/service-auth-model.md`
- `docs/dev/service-contracts.md`
- `docs/dev/execution-contract.md`
- `docs/dev/engine-implementation-contract.md`
- `docs/dev/state-machine.md`

Operations:

- `docs/ops/prefect-server.md`
- `docs/ops/storage-node.md`

## Conceptual topology

- Prefect server node:
  - Prefect API/UI + metadata DB
  - deployment registration + orchestration state
- Worker nodes:
  - fixed docker worker (`gpu-fixed`)
  - optional colab workers (`gpu-colab`)
- Storage node:
  - MinIO + worker-router + MLflow
  - artifact/object persistence and worker-facing auth/presign routing

Core interaction path:

1. register deployment to Prefect
2. submit flow run to work pool/queue
3. worker executes the registered engine deployment or the compatibility wrapper
4. worker requests presigned URLs via `storage-api` and uploads objects through `storage-api` signed object paths
5. worker records run metadata via `storage-api/mlflow`
6. flush exports completed run snapshots to storage
7. prune handles retention (optional apply mode)

Standard validation path:

1. run the standard Prefect dummy smoke
2. verify artifact objects and MLflow linkage

```bash
./bin/cli observability fixed-dummy-smoke --deployment-name discoverex-engine-run --timeout-sec 240
uv run python scripts/observability/prefect_verify_standard_dummy_run.py --flow-run-id <FLOW_RUN_ID>
```

## Local quickstart (dev)

```bash
cp .env.example .env
set -a; source .env; set +a
mkdir -p "${MINIO_DATA_DIR}"
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml build base-runtime
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml up -d --build minio prefect worker-router worker
```

Register deployment and run:

```bash
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect work-pool create gpu-pool --type process || true
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml run --rm register
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment run 'run-job/discoverex-engine-run' \
  -p job_spec_json='{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo hello-prefect"],"config":null,"inputs":{},"env":{},"outputs_prefix":null}'
```

Inspect deployment and workers:

```bash
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment ls
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml logs worker --tail=80
```

`run_job` flow supports optional checkpoint resume parameters:

- `resume_key`: stable key for restart/continue
- `checkpoint_dir`: directory where step state is persisted (`<resume_key>.json`)

Example:

```bash
prefect deployment run 'run-job/discoverex-engine-run' \
  -p job_spec_json='{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo hello-prefect"],"config":null,"inputs":{},"env":{},"outputs_prefix":null}' \
  -p resume_key='job-001' \
  -p checkpoint_dir='/content/drive/MyDrive/orchestrator/checkpoints'
```

## Colab worker quickstart

Primary operation should be script-first:

```bash
PYTHONPATH=src python infra/stacks/worker/colab/colab_worker_runner.py bootstrap \
  --repo-dir /content/drive/MyDrive/discoverex/orchestrator \
  --cache-root /content/drive/MyDrive/discoverex/cache \
  --venv-dir /content/venv

/content/venv/bin/python infra/stacks/worker/colab/colab_worker_runner.py start \
  --skip-install \
  --checkpoint-dir /content/drive/MyDrive/orchestrator/checkpoints
```

The runtime layout is:

- repo: Google Drive
- pip/XDG cache: Google Drive
- virtualenv: `/content/venv`

The runner auto-loads repo-root `.env` when present and creates the checkpoint
directory after Drive is mounted. Do not create the virtualenv on Google Drive.

Other commands:

```bash
/content/venv/bin/python infra/stacks/worker/colab/colab_worker_runner.py status
/content/venv/bin/python infra/stacks/worker/colab/colab_worker_runner.py logs --tail 80
/content/venv/bin/python infra/stacks/worker/colab/colab_worker_runner.py stop
```

Optional notebook: `infra/stacks/worker/colab/worker_colab.ipynb`
It keeps only minimal bootstrap logic inline: the notebook can begin from a
session where only the notebook file is present, configure env, clone or
refresh the repo into Drive, and then invoke the checked-out
`infra/stacks/worker/colab/colab_worker_runner.py` with Colab-visible logs.

Artifact and experiment policy:

- Record experiment metadata in MLflow (params/metrics/tags/status).
- Prefer `STORAGE_API_URL/artifact/...` for storage presigns.
- Upload and download artifact bytes through object-store presigned URLs, not through router proxying.
- Keep MinIO credentials out of workers.
- Persist uploaded `object_uri` references into MLflow tags (for example `artifact_manifest_uri`).
- In repo run mode, the runner now checks out the requested `ref` instead of detaching strictly by resolved SHA.

Auth split:

- External access credentials: `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`
- Internal backend secrets stay on the storage node gateway/backend services only

## Storage-only production profile

Use this when this machine is dedicated storage node:

```bash
./bin/cli runtime init storage
cp infra/stacks/storage-node/.env.example infra/stacks/storage-node/.env
set -a; source infra/stacks/storage-node/.env; set +a
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml build base-runtime
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml up -d
```

Operational runbook: `docs/ops/storage-node.md`
This profile now exposes `storage.discoverex.qzz.io` for human UI access and `storage-api.discoverex.qzz.io` for machine APIs/object paths, while keeping object and MLflow credentials on the storage node only.

## Prefect server production profile (VM)

Use this when this machine is dedicated Prefect control plane:

```bash
cp infra/stacks/prefect-server/.env.example infra/stacks/prefect-server/.env
# fill PREFECT_SERVER_IMAGE + VM-local DB + flush values
./bin/cli prefect up
./bin/cli prefect ps
./bin/cli prefect flush
./bin/cli prefect prune
```

Runbook: `docs/ops/prefect-server.md`

## Internal CLI shortcuts

`bin/cli` is the canonical internal operator command:

```bash
./bin/cli runtime init all
./bin/cli e2e local mlflow --keep-on-fail
./bin/cli e2e remote dummy --prefect-api-url https://prefect.example.com/api
./bin/cli e2e remote engine --prefect-api-url https://prefect.example.com/api --prune-mode apply
./bin/cli storage up
./bin/cli storage down
./bin/cli local up
./bin/cli prefect up
./bin/cli prefect logs
./bin/cli prefect flush
./bin/cli prefect prune
./bin/cli register run
./bin/cli worker fixed up
./bin/cli worker register-gpu
./bin/cli worker submit --job-spec-json '{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo hello"]}'
```

Runtime data policy:

- Run internal commands from project root (`orchestrator`).
- Keep runtime data outside repo under `../runtime` (for example `../runtime/storage`, `../runtime/worker`).

Remote Prefect VM control is now absorbed into `bin/cli` domain commands:

```bash
./bin/cli ops connect
./bin/cli prefect install --remote
./bin/cli prefect up --remote
./bin/cli prefect ps --remote
./bin/cli prefect logs --remote
./bin/cli prefect workers --remote
```

Remote Prefect actions run under `REMOTE_PREFECT_PATH` (default:
`/opt/services/orchestrator-prefect`) and use `REMOTE_PREFECT_ENV` /
`REMOTE_PREFECT_COMPOSE` defaults (`.env`, `docker-compose.yml`).
`cli prefect install --remote` still uses `REMOTE_PROJECT_PATH` because it bootstraps from the repo checkout.

`bin/orchestrator` remains reserved for external-facing CLI responsibilities. Internal docker, ssh, and orchestration operations should stay under `bin/cli`.

## Test

```bash
uv run ruff check .
uv run pytest -q
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/contract
```

E2E (register -> worker -> storage, optional MLflow/external):

```bash
# core chain (local)
scripts/e2e/e2e_local_orchestrator.sh --mode core

# core + mlflow metadata verification
scripts/e2e/e2e_local_orchestrator.sh --mode mlflow
```

`mlflow` mode starts a local MLflow container from the local e2e compose and validates
MLflow run/tag linkage without external endpoints.

Remote Prefect + local storage E2E (production-worker oriented):

```bash
# control-plane dummy path: register + dummy run + storage verify + flush + prune dry-run
./bin/cli e2e remote dummy \
  --prefect-api-url https://prefect.example.com/api

# full engine path: register + real engine job + storage verify + flush + prune dry-run
./bin/cli e2e remote engine \
  --prefect-api-url https://prefect.example.com/api

# PoC mode for full engine path (allow prune apply)
./bin/cli e2e remote engine \
  --prefect-api-url https://prefect.example.com/api \
  --prune-mode apply \
  --prune-ttl-hours 0
```

Notes:

- `remote dummy` uses the checked-in inline dummy job spec and does not require the external engine helper script.
- `remote engine` keeps the previous behavior and builds a repo-based engine job spec through the external engine helper.
- `./bin/cli e2e remote ...` without an explicit mode is kept as an alias for `remote engine`.
- Both flows assume an existing operational worker in the target work pool unless `--bootstrap-worker` is used.
- `--bootstrap-worker` is available only for temporary bootstrapping and should be removed during production cutover.
- Workers should use `STORAGE_API_URL` for storage and `MLFLOW_TRACKING_URI=https://storage-api.../mlflow` for MLflow.
