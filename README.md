# orchestrator

Prefect-based orchestration workspace with four responsibilities:

- `flows`: Prefect workflow definitions (`engine_run_flow`)
- `runner`: git checkout (resolved commit) + entrypoint execution
- `storage`: hexagonal storage module for presign/head control-plane logic
- `worker_router`: worker-facing auth gateway for storage control APIs and MLflow

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
3. worker executes `engine_run_flow`
4. worker requests presigned URLs via `storage-api` or `worker-router` compatibility path and uploads objects directly to object storage
5. worker records run metadata via MLflow (direct or router-backed proxy)
6. flush exports completed run snapshots to storage
7. prune handles retention (optional apply mode)

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
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment run 'engine-run/engine-run' \
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
prefect deployment run 'engine-run/engine-run' \
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
./bin/project runtime init storage
cp infra/stacks/storage-node/.env.example infra/stacks/storage-node/.env
set -a; source infra/stacks/storage-node/.env; set +a
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml build base-runtime
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml up -d
```

Operational runbook: `docs/ops/storage-node.md`
This profile now exposes `storage.discoverex.qzz.io` for human access, `storage-api.discoverex.qzz.io` for machine presign access, and keeps object credentials on the storage node only.

## Prefect server production profile (VM)

Use this when this machine is dedicated Prefect control plane:

```bash
cp infra/stacks/prefect-server/.env.example infra/stacks/prefect-server/.env
# fill PREFECT_SERVER_IMAGE + VM-local DB + flush values
./bin/project prefect up
./bin/project prefect ps
./bin/project prefect flush
./bin/project prefect prune
```

Runbook: `docs/ops/prefect-server.md`

## Project command shortcuts

`bin/project` is the canonical local operator command:

```bash
./bin/project runtime init all
./bin/project e2e mlflow --keep-on-fail
./bin/project e2e-remote --prefect-api-url https://prefect.example.com/api --prune-mode apply
./bin/project storage up
./bin/project storage down
./bin/project prefect up
./bin/project prefect logs
./bin/project prefect flush
./bin/project prefect prune
./bin/project register run
./bin/project worker fixed up
./bin/project worker register-gpu
./bin/project worker submit --job-spec-json '{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo hello"]}'
```

Runtime data policy:

- Run commands from project root (`orchestrator`).
- Keep runtime data outside repo under `../runtime` (for example `../runtime/storage`, `../runtime/worker`).

`bin/remote` provides remote VM control for Prefect stack:

```bash
./bin/remote connect
./bin/remote prefect-install
./bin/remote prefect-up
./bin/remote prefect-ps
./bin/remote prefect-logs
./bin/remote worker ps
```

`prefect-*` commands run under `REMOTE_PREFECT_PATH` (default:
`/opt/services/orchestrator-prefect`) and use remote-specific
`REMOTE_PREFECT_ENV` / `REMOTE_PREFECT_COMPOSE` defaults (`.env`,
`docker-compose.yml`).
`prefect-install` still uses `REMOTE_PROJECT_PATH` because it bootstraps from the repo checkout.

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
# register + run + storage verify + flush + prune dry-run
./bin/project e2e-remote \
  --prefect-api-url https://prefect.example.com/api

# PoC mode (allow prune apply)
./bin/project e2e-remote \
  --prefect-api-url https://prefect.example.com/api \
  --prune-mode apply \
  --prune-ttl-hours 0
```

Notes:

- Default flow assumes an existing operational worker in the target work pool.
- `--bootstrap-worker` is available only for temporary bootstrapping and should be removed during production cutover.
- Worker router mode is the preferred production path for storage and MLflow access from workers.
