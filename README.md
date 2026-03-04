# orchestrator

Prefect-based orchestration workspace with three responsibilities:

- `flows`: Prefect workflow definitions (`engine_run_flow`)
- `runner`: git checkout (resolved commit) + entrypoint execution
- `storage_gateway`: presigned URL gateway for MinIO (workers never hold MinIO credentials)

## Local quickstart (dev)

```bash
cp .env.example .env
uv sync
set -a; source .env; set +a
docker compose -f docker-compose.local.yml up -d minio prefect
uv run uvicorn storage_gateway.main:app --app-dir src --port ${STORAGE_GATEWAY_PORT:-18100}
```

In another terminal:

```bash
set -a; source .env; set +a
prefect config set PREFECT_API_URL=$PREFECT_API_URL
prefect work-pool create $PREFECT_WORK_POOL --type process
prefect worker start --pool $PREFECT_WORK_POOL --type process
```

Register deployment and run:

```bash
set -a; source .env; set +a
PYTHONPATH=src uv run python -m deployments.register --pool $PREFECT_WORK_POOL
prefect deployment run 'engine-run/engine-run' \
  -p repo_url='https://github.com/octocat/Hello-World.git' \
  -p ref='master' \
  -p entrypoint='["/bin/sh","-lc","echo hello-prefect"]'
```

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
