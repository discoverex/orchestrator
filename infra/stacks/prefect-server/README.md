# Prefect Server Stack (VM)

This stack runs Prefect server + Cloudflare Tunnel on a VM for external workers.

## 1) Configure

```bash
cp infra/stacks/prefect-server/.env.example infra/stacks/prefect-server/.env
# edit infra/stacks/prefect-server/.env
# copy tunnel credentials json into infra/stacks/prefect-server/.cloudflared/
```

`PREFECT_API_DATABASE_CONNECTION_URL` must point to the shared Postgres instance.
Use logical DB/user separation (for example: database `prefect`, user `prefect_user`).

## 2) Start/stop

```bash
./bin/project prefect up
./bin/project prefect ps
./bin/project prefect logs
./bin/project prefect down
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

- `PREFECT_API_URL=https://<PREFECT_HOSTNAME>/api`
- Cloudflare Access service token headers:
  - `CF-Access-Client-Id`
  - `CF-Access-Client-Secret`

Apply Cloudflare Access policy so worker tokens can call Prefect API endpoints.
