#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

uv sync

docker compose -f docker-compose.local.yml up -d minio prefect

echo "[0/6] Wait for minio/prefect health"
for i in $(seq 1 60); do
  MINIO_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' orchestrator-minio 2>/dev/null || echo "starting")
  PREFECT_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' orchestrator-prefect 2>/dev/null || echo "starting")
  if [ "$MINIO_HEALTH" = "healthy" ] && [ "$PREFECT_HEALTH" = "healthy" ]; then
    break
  fi
  sleep 1
done

echo "[1/6] Start storage gateway"
GATEWAY_PORT=${STORAGE_GATEWAY_PORT:-18100}
uv run uvicorn storage_gateway.main:app --app-dir src --port "$GATEWAY_PORT" >/tmp/orchestrator-storage-gateway.log 2>&1 &
GATEWAY_PID=$!
trap 'kill $GATEWAY_PID >/dev/null 2>&1 || true' EXIT

for i in $(seq 1 30); do
  if curl -sS -m 2 "http://127.0.0.1:${GATEWAY_PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "[2/6] Configure prefect"
uv run prefect config set PREFECT_API_URL=${PREFECT_API_URL:-http://127.0.0.1:14200/api} >/dev/null
uv run prefect work-pool create ${PREFECT_WORK_POOL:-colab-gpu} --type process >/dev/null 2>&1 || true

echo "[3/6] Start worker"
uv run prefect worker start --pool ${PREFECT_WORK_POOL:-colab-gpu} --type process >/tmp/orchestrator-prefect-worker.log 2>&1 &
WORKER_PID=$!
trap 'kill $GATEWAY_PID $WORKER_PID >/dev/null 2>&1 || true' EXIT
sleep 3

echo "[4/6] Register deployment"
PYTHONPATH=src uv run python -m deployments.register --pool ${PREFECT_WORK_POOL:-colab-gpu}

echo "[5/6] Submit run"
uv run prefect deployment run 'engine-run/engine-run' \
  -p repo_url='https://github.com/octocat/Hello-World.git' \
  -p ref='master' \
  -p entrypoint='["/bin/sh","-lc","echo hello-prefect"]' >/tmp/orchestrator-prefect-run.log

sleep 10

echo "[6/6] Verify minio object exists"
uv run python - <<'PY'
import os
from minio import Minio

endpoint = os.getenv("MINIO_ENDPOINT", "127.0.0.1:19000")
client = Minio(
    endpoint,
    access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
    secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
)

bucket = os.getenv("ARTIFACT_BUCKET", "orchestrator-artifacts")
if not client.bucket_exists(bucket):
    raise SystemExit(f"missing bucket: {bucket}")

found = False
for obj in client.list_objects(bucket, prefix="jobs/", recursive=True):
    if obj.object_name.endswith("stdout.log"):
        print(f"found: s3://{bucket}/{obj.object_name}")
        found = True
        break

if not found:
    raise SystemExit("stdout.log not found")
PY

echo "E2E done"
