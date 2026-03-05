# Prefect Server Stack (VM)

This stack runs Prefect server + VM-local Postgres.
It also runs maintenance to flush completed runs to storage-node and prune old VM data.

## 1) Configure

```bash
cp infra/stacks/prefect-server/.env.example infra/stacks/prefect-server/.env
# edit infra/stacks/prefect-server/.env
./bin/project prefect build
```

`prefect-db` is part of this stack. Set `PREFECT_DB_*` values in `.env`.
Completed runs are exported as full JSON snapshots using:

- `FLUSH_TARGET_URL` (storage-gateway base URL)
- `FLUSH_GATEWAY_TOKEN`

## 2) Start/stop

```bash
./bin/project prefect up
./bin/project prefect ps
./bin/project prefect logs
./bin/project prefect down
./bin/project prefect flush
./bin/project prefect prune
```

## 3) VM bootstrap (remote)

```bash
./bin/remote prefect-install
./bin/remote prefect-up
./bin/remote prefect-ps
./bin/remote prefect-logs
```

`bin/remote` reads `REMOTE_USERNAME`, `REMOTE_HOST`, and `GITHUB_DEPLOY_KEY_PATH`
from root `.env` by default.

## 4) Worker settings

External workers should use:

- `PREFECT_API_URL=https://<your-domain>/api`
- If Cloudflare Access is enabled on the domain, pass service token headers:
  - `CF-Access-Client-Id`
  - `CF-Access-Client-Secret`
