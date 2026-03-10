# Storage Node Operations

This machine is storage-only in production:

- MinIO (object SSOT)
- worker-router (storage auth gateway + presign issuer + MLflow routing)
- MLflow Tracking server
- MLflow metadata Postgres

Prefect server must run on another node.

## 1) Deploy (production profile)

```bash
./bin/project runtime init storage
cp infra/stacks/storage-node/.env.example infra/stacks/storage-node/.env
# fill strong secrets, MLflow DB, and Cloudflare values
set -a; source infra/stacks/storage-node/.env; set +a
mkdir -p "${MINIO_DATA_DIR}" "${MLFLOW_DB_DATA_DIR}" "${BACKUP_ROOT}"

docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml build base-runtime
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml build worker-router
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml up -d
```

Runtime policy:

- Keep compose/scripts/env files in `orchestrator`.
- Keep runtime data in parent `../runtime/storage` (default via `.env.example`).

## 2) Access model

- Public exposure: `storage.discoverex.qzz.io` (human CF/email access), `storage-api.discoverex.qzz.io` (machine CF service-token access), `mlflow.discoverex.qzz.io` (MLflow)
- Direct exposure forbidden: MinIO API and console must stay localhost-bound
- Runtime isolation: worker-router runs from a built image and owns storage control-plane composition
- MLflow worker endpoint: `MLFLOW_TRACKING_URI=https://mlflow.discoverex.qzz.io`
- MLflow auth model: Cloudflare Access(Service Token) only
- Artifact policy: worker presign/head requests go through storage routes on worker-router, issued upload/download URLs go directly to the object endpoint
- MLflow responsibility: metadata only (params/metrics/tags/status). Do not use `mlflow.log_artifact()`.
- MinIO operator access should use localhost-bound console port or a separately protected operator ingress.
- Worker contract: workers should carry only `STORAGE_API_URL`/`WORKER_ROUTER_URL` and Cloudflare Access credentials; direct storage/MLflow credentials stay on this node.
- Request auth on storage API:

1. Cloudflare Access headers (`CF-Access-Client-Id`, `CF-Access-Client-Secret`) when `GATEWAY_REQUIRE_CF_ACCESS=true`

Cloudflare side requirements for MLflow:

1. Create DNS/route for `mlflow.discoverex.qzz.io` in the same tunnel
2. Add/verify tunnel ingress for `mlflow.discoverex.qzz.io -> http://mlflow:${MLFLOW_PORT}`
3. Create Cloudflare Access application for `mlflow.discoverex.qzz.io`
4. Issue Service Token and distribute only to trusted workers/clients

Note: `infra/stacks/storage-node/.cloudflared/config.yml` is template-style (`__MLFLOW_PORT__`).
`docker-compose` starts cloudflared with runtime substitution from `MLFLOW_PORT`.

## 3) Health checks

```bash
curl -fsS http://127.0.0.1:8200/healthz
curl -fsS http://127.0.0.1:${MINIO_API_PORT}/minio/health/live
docker compose --env-file infra/stacks/storage-node/.env -f infra/stacks/storage-node/docker-compose.yml exec -T mlflow \
  python -c "import os, urllib.request; p=os.environ.get('MLFLOW_PORT','5000'); urllib.request.urlopen(f'http://localhost:{p}/', timeout=3)"
```

Worker-router path quick check:

```bash
set -a; source infra/stacks/storage-node/.env; set +a
curl -fsS -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
  http://127.0.0.1:8200/mlflow/api/2.0/mlflow/experiments/search
```

## 4) MLflow verification

```bash
set -a; source infra/stacks/storage-node/.env; set +a

# 0) DNS resolution must work before E2E full mode
getent ahosts mlflow.discoverex.qzz.io

# 1) Access check (without CF token should be blocked by Access policy)
curl -I https://mlflow.discoverex.qzz.io

# 2) Access check (with Service Token)
curl -fsS \
  -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
  https://mlflow.discoverex.qzz.io/api/2.0/mlflow/experiments/search

# 3) Worker run check
export MLFLOW_TRACKING_URI=https://mlflow.discoverex.qzz.io
# run mlflow.start_run(), then:
# - log param/metric/tag only
# - upload files via storage-api-issued presigned URLs
# - save returned object_uri values as MLflow tags (artifact_manifest_uri, artifact_stdout_uri, ...)
```

If it fails at `mlflow.verify_tags` with `mlflow runs/create failed: HTTP 403`,
Cloudflare Access policy is still blocking MLflow write APIs for the service token.

If worker-side artifact preparation fails with `non-json response from storage API`,
inspect `worker-router` logs first; that now usually indicates an auth or upstream routing mismatch rather than a worker bug.

## 5) Backup (daily, retain 30 days)

```bash
set -a; source infra/stacks/storage-node/.env; set +a
uv run python scripts/ops/storage_backup.py
```

Recommend cron:

```cron
15 2 * * * cd /home/esillileu/discoverex/orchestrator && /usr/bin/env bash -lc 'set -a; source infra/stacks/storage-node/.env; set +a; uv run python scripts/ops/storage_backup.py >> ../runtime/storage/logs/backup.log 2>&1'
```

## 6) Restore drill (weekly)

```bash
set -a; source infra/stacks/storage-node/.env; set +a
uv run python scripts/ops/storage_restore_drill.py
```

This creates a temporary `restore-drill-*` bucket and verifies sampled checksums.

## 7) Alerts to wire

- gateway 5xx rate > threshold
- mlflow 5xx rate > threshold
- MinIO healthcheck fail
- MLflow DB healthcheck fail
- disk usage > 85%
- backup script non-zero exit
