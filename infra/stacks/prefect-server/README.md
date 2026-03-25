# Prefect Server Stack (VM)

This stack runs Prefect server + VM-local Postgres.
It also runs maintenance to flush completed runs to storage-node and prune old VM data.

## 1) Configure

```bash
cp infra/stacks/prefect-server/.env.example infra/stacks/prefect-server/.env
# edit infra/stacks/prefect-server/.env
./bin/cli prefect build
```

`prefect-db` is part of this stack. Set `PREFECT_DB_*` values in `.env`.
Completed runs are exported as full JSON snapshots using:

- `FLUSH_TARGET_URL` (public gateway `/storage` base URL)

## 2) Start/stop

```bash
./bin/cli prefect up
./bin/cli prefect ps
./bin/cli prefect logs
./bin/cli prefect down
./bin/cli prefect flush
./bin/cli prefect prune
```

## 3) VM bootstrap (remote)

```bash
./bin/cli prefect install --remote
./bin/cli prefect up --remote
./bin/cli prefect ps --remote
./bin/cli prefect logs --remote
```

`bin/cli` reads `REMOTE_USERNAME`, `REMOTE_HOST`, and `GITHUB_DEPLOY_KEY_PATH`
from root `.env` by default.

## 4) Worker settings

External workers should use:

- `PREFECT_API_URL=https://<your-domain>/api`
- `PREFECT_WORK_POOL=gpu-pool`
- `PREFECT_WORK_QUEUE=gpu-fixed` (fixed) or `gpu-colab` (burst)
- If Cloudflare Access is enabled on the domain, pass service token headers:
  - `CF-Access-Client-Id`
  - `CF-Access-Client-Secret`
