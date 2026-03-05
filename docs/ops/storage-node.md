# Storage Node Operations

This machine is storage-only in production:

- MinIO (object SSOT)
- storage-gateway (presigned URL API)
- MLflow Tracking server
- MLflow metadata Postgres

Prefect server must run on another node.

## 1) Deploy (production profile)

```bash
cp infra/storage-node/.env.example infra/storage-node/.env
# fill strong secrets, MLflow DB, and Cloudflare values
set -a; source infra/storage-node/.env; set +a
mkdir -p "${MINIO_DATA_DIR}" "${MLFLOW_DB_DATA_DIR}" "${BACKUP_ROOT}"

docker compose --env-file infra/storage-node/.env -f infra/storage-node/docker-compose.yml build storage-gateway
docker compose --env-file infra/storage-node/.env -f infra/storage-node/docker-compose.yml up -d
```

## 2) Access model

- Public exposure: Cloudflare Tunnel -> `discoverex.qzz.io` (storage-gateway), `mlflow.discoverex.qzz.io` (MLflow)
- Direct exposure forbidden: MinIO API and console must stay localhost-bound
- Runtime isolation: storage-gateway runs from a built image (no project source bind-mount, no host `.venv` reuse)
- Presign URL mode: `PRESIGN_MODE=gateway` (gateway proxy URL issuance for external clients)
- MLflow worker endpoint: `MLFLOW_TRACKING_URI=https://mlflow.discoverex.qzz.io`
- MLflow auth model: Cloudflare Access(Service Token) only
- Artifact policy: all file upload/download must go through `storage-gateway` (single entrypoint)
- MLflow responsibility: metadata only (params/metrics/tags/status). Do not use `mlflow.log_artifact()`.
- Optional local explorer:
  - `STORAGE_EXPLORER_ENABLED=true`
  - `STORAGE_EXPLORER_LOCAL_ONLY=true`
  - open `http://127.0.0.1:${STORAGE_GATEWAY_PORT}/explorer`
- Request auth on gateway:

1. Bearer token (`Authorization`)
2. Cloudflare Access headers (`CF-Access-Client-Id`, `CF-Access-Client-Secret`) when `GATEWAY_REQUIRE_CF_ACCESS=true`

Cloudflare side requirements for MLflow:

1. Create DNS/route for `mlflow.discoverex.qzz.io` in the same tunnel
2. Add/verify tunnel ingress for `mlflow.discoverex.qzz.io -> http://mlflow:5000`
3. Create Cloudflare Access application for `mlflow.discoverex.qzz.io`
4. Issue Service Token and distribute only to trusted workers/clients

## 3) Health checks

```bash
curl -fsS http://127.0.0.1:${STORAGE_GATEWAY_PORT}/healthz
curl -fsS http://127.0.0.1:${MINIO_API_PORT}/minio/health/live
docker compose --env-file infra/storage-node/.env -f infra/storage-node/docker-compose.yml exec -T mlflow curl -fsS http://localhost:5000/
```

## 4) MLflow verification

```bash
set -a; source infra/storage-node/.env; set +a

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
# - upload files via storage-gateway
# - save returned object_uri values as MLflow tags (artifact_manifest_uri, artifact_stdout_uri, ...)
```

If `scripts/e2e_orchestrator.sh --mode full` fails at `verify-full-prereqs`,
fix `.env` keys and DNS resolution first before retrying.

If it fails at `verify-mlflow-tags` with `mlflow runs/create failed: HTTP 403`,
Cloudflare Access policy is still blocking MLflow write APIs for the service token.

## 5) Backup (daily, retain 30 days)

```bash
set -a; source infra/storage-node/.env; set +a
uv run python scripts/storage_backup.py
```

Recommend cron:

```cron
15 2 * * * cd /home/esillileu/discoverex/orchestrator && /usr/bin/env bash -lc 'set -a; source infra/storage-node/.env; set +a; uv run python scripts/storage_backup.py >> /home/esillileu/discoverex/data/backups/backup.log 2>&1'
```

## 6) Restore drill (weekly)

```bash
set -a; source infra/storage-node/.env; set +a
uv run python scripts/storage_restore_drill.py
```

This creates a temporary `restore-drill-*` bucket and verifies sampled checksums.

## 7) Alerts to wire

- gateway 5xx rate > threshold
- mlflow 5xx rate > threshold
- MinIO healthcheck fail
- MLflow DB healthcheck fail
- disk usage > 85%
- backup script non-zero exit
