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
docker compose -f docker-compose.local.yml up -d --build minio prefect storage-gateway worker
```

Register deployment and run:

```bash
docker compose -f docker-compose.local.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect work-pool create ${PREFECT_WORK_POOL:-colab-gpu} --type process || true
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

Colab notebook is provided at `notebooks/worker_colab.ipynb`.

For scripted startup in Colab:

```bash
PYTHONPATH=src uv run python scripts/colab_worker_runner.py start \
  --checkpoint-dir /content/drive/MyDrive/orchestrator/checkpoints
```

Other commands:

```bash
PYTHONPATH=src uv run python scripts/colab_worker_runner.py status
PYTHONPATH=src uv run python scripts/colab_worker_runner.py logs --tail 80
PYTHONPATH=src uv run python scripts/colab_worker_runner.py stop
```

Artifact and experiment policy:

- Record experiment metadata in MLflow (params/metrics/tags/status).
- Upload files only through `storage-gateway` (`/v1/presign/*`, `/v1/object/proxy`).
- Keep MinIO credentials out of workers.
- Persist uploaded `object_uri` references into MLflow tags (for example `artifact_manifest_uri`).

## Storage-only production profile

Use this when this machine is dedicated storage node:

```bash
cp infra/storage-node/.env.example infra/storage-node/.env
set -a; source infra/storage-node/.env; set +a
docker compose --env-file infra/storage-node/.env -f infra/storage-node/docker-compose.yml up -d
```

Operational runbook: `docs/ops/storage-node.md`

## Test

```bash
uv run ruff check .
uv run pytest tests -q
```

E2E (register -> worker -> storage, optional MLflow/external):

```bash
# core chain (local)
scripts/e2e_orchestrator.sh --mode core

# core + mlflow metadata verification
MLFLOW_TRACKING_URI=http://127.0.0.1:5000 scripts/e2e_orchestrator.sh --mode mlflow

# full external path (Cloudflare Access)
MLFLOW_TRACKING_URI=https://mlflow.discoverex.qzz.io \
MLFLOW_PUBLIC_URL=https://mlflow.discoverex.qzz.io \
CF_ACCESS_CLIENT_ID=... \
CF_ACCESS_CLIENT_SECRET=... \
scripts/e2e_orchestrator.sh --mode full
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
