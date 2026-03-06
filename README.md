# orchestrator

Prefect-based orchestration workspace with three responsibilities:

- `flows`: Prefect workflow definitions (`engine_run_flow`)
- `runner`: git checkout (resolved commit) + entrypoint execution
- `storage_gateway`: presigned URL gateway for MinIO (workers never hold MinIO credentials)

## Local quickstart (dev)

```bash
cp .env.example .env
set -a; source .env; set +a
mkdir -p "${MINIO_DATA_DIR}"
docker compose -f docker-compose.local.yml build base-runtime
docker compose -f docker-compose.local.yml up -d --build minio prefect storage-gateway worker
```

Register deployment and run:

```bash
docker compose -f docker-compose.local.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect work-pool create ${PREFECT_WORK_POOL:-gpu-pool} --type process || true
docker compose -f docker-compose.local.yml run --rm register
docker compose -f docker-compose.local.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment run 'engine-run/engine-run' \
  -p repo_url='https://github.com/octocat/Hello-World.git' \
  -p ref='master' \
  -p entrypoint='["/bin/sh","-lc","echo hello-prefect"]'
```

Inspect deployment and workers:

```bash
docker compose -f docker-compose.local.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment ls
docker compose -f docker-compose.local.yml logs worker --tail=80
```

`engine_run_flow` supports optional checkpoint resume parameters:

- `resume_key`: stable key for restart/continue
- `checkpoint_dir`: directory where step state is persisted (`<resume_key>.json`)

Example:

```bash
prefect deployment run 'engine-run/engine-run' \
  -p repo_url='https://github.com/octocat/Hello-World.git' \
  -p ref='master' \
  -p entrypoint='["/bin/sh","-lc","echo hello-prefect"]' \
  -p resume_key='job-001' \
  -p checkpoint_dir='/content/drive/MyDrive/orchestrator/checkpoints'
```

## Colab worker quickstart

Primary operation should be script-first:

```bash
PYTHONPATH=src python infra/stacks/worker/colab/colab_worker_runner.py start \
  --checkpoint-dir /content/drive/MyDrive/orchestrator/checkpoints
```

Other commands:

```bash
PYTHONPATH=src python infra/stacks/worker/colab/colab_worker_runner.py status
PYTHONPATH=src python infra/stacks/worker/colab/colab_worker_runner.py logs --tail 80
PYTHONPATH=src python infra/stacks/worker/colab/colab_worker_runner.py stop
```

Optional notebook: `infra/stacks/worker/colab/worker_colab.ipynb`

Artifact and experiment policy:

- Record experiment metadata in MLflow (params/metrics/tags/status).
- Upload files only through `storage-gateway` (`/v1/presign/*`, `/v1/object/proxy`).
- Keep MinIO credentials out of workers.
- Persist uploaded `object_uri` references into MLflow tags (for example `artifact_manifest_uri`).

## Storage-only production profile

Use this when this machine is dedicated storage node:

```bash
cp infra/stacks/storage-node/.env.example infra/stacks/storage-node/.env
set -a; source infra/stacks/storage-node/.env; set +a
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml build base-runtime
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml up -d
```

Operational runbook: `docs/ops/storage-node.md`

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
./bin/project e2e full --keep-on-fail
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
./bin/project worker submit --repo-url https://github.com/octocat/Hello-World.git --ref master
```

`bin/remote` provides remote VM control for Prefect stack:

```bash
./bin/remote connect
./bin/remote prefect-install
./bin/remote prefect-up
./bin/remote prefect-ps
./bin/remote prefect-logs
```

## Test

```bash
uv run ruff check .
uv run pytest tests -q
```

E2E (register -> worker -> storage, optional MLflow/external):

```bash
# core chain (local)
scripts/e2e/e2e_orchestrator.sh --mode core

# core + mlflow metadata verification
MLFLOW_TRACKING_URI=http://127.0.0.1:5000 scripts/e2e/e2e_orchestrator.sh --mode mlflow

# full external path (Cloudflare Access)
MLFLOW_TRACKING_URI=https://mlflow.discoverex.qzz.io \
MLFLOW_PUBLIC_URL=https://mlflow.discoverex.qzz.io \
CF_ACCESS_CLIENT_ID=... \
CF_ACCESS_CLIENT_SECRET=... \
scripts/e2e/e2e_orchestrator.sh --mode full
```

`full` mode now fails fast when required env keys are missing or DNS does not resolve for
`MLFLOW_TRACKING_URI`/`MLFLOW_PUBLIC_URL`.

Recommended pre-check:

```bash
set -a; source .env; set +a
getent ahosts mlflow.discoverex.qzz.io
curl -fsSI https://mlflow.discoverex.qzz.io \
  -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}"
```

If `verify-mlflow-tags` fails with `mlflow runs/create failed: HTTP 403`, adjust
Cloudflare Access policy to allow MLflow write APIs for the configured service token.

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
