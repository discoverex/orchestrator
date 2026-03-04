# Storage Node Operations

This machine is storage-only in production:

- MinIO (object SSOT)
- storage-gateway (presigned URL API)

Prefect server must run on another node.

## 1) Deploy (production profile)

```bash
cp infra/storage-node/.env.example infra/storage-node/.env
# fill strong secrets and Cloudflare Access values
mkdir -p /home/esillileu/discoverex/data/minio /home/esillileu/discoverex/data/backups/minio
set -a; source infra/storage-node/.env; set +a

docker compose --env-file infra/storage-node/.env -f infra/storage-node/docker-compose.yml up -d
```

## 2) Access model

- Public exposure: Cloudflare Tunnel -> storage-gateway only
- Direct exposure forbidden: MinIO API and console must stay localhost-bound
- Presign URL mode: `PRESIGN_MODE=gateway` (gateway proxy URL issuance for external clients)
- Optional local explorer:
  - `STORAGE_EXPLORER_ENABLED=true`
  - `STORAGE_EXPLORER_LOCAL_ONLY=true`
  - open `http://127.0.0.1:${STORAGE_GATEWAY_PORT}/explorer`
- Request auth on gateway:

1. Bearer token (`Authorization`)
2. Cloudflare Access headers (`CF-Access-Client-Id`, `CF-Access-Client-Secret`) when `GATEWAY_REQUIRE_CF_ACCESS=true`

## 3) Health checks

```bash
curl -fsS http://127.0.0.1:${STORAGE_GATEWAY_PORT}/healthz
curl -fsS http://127.0.0.1:${MINIO_API_PORT}/minio/health/live
```

## 4) Backup (daily, retain 30 days)

```bash
set -a; source infra/storage-node/.env; set +a
uv run python scripts/storage_backup.py
```

Recommend cron:

```cron
15 2 * * * cd /home/esillileu/discoverex/orchestrator && /usr/bin/env bash -lc 'set -a; source infra/storage-node/.env; set +a; uv run python scripts/storage_backup.py >> /home/esillileu/discoverex/data/backups/backup.log 2>&1'
```

## 5) Restore drill (weekly)

```bash
set -a; source infra/storage-node/.env; set +a
uv run python scripts/storage_restore_drill.py
```

This creates a temporary `restore-drill-*` bucket and verifies sampled checksums.

## 6) Alerts to wire

- gateway 5xx rate > threshold
- MinIO healthcheck fail
- disk usage > 85%
- backup script non-zero exit
