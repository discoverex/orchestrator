# Prefect Server Operations

This node runs control-plane services only:

- Prefect API/UI server
- Cloudflare Tunnel sidecar

Workers stay fully separate and poll work from Prefect over HTTPS.

## 1) Database setup (once)

Use shared Postgres with logical separation:

```sql
\i scripts/ops/prefect_db_init.sql
```

Then set `PREFECT_API_DATABASE_CONNECTION_URL` in
`infra/stacks/prefect-server/.env`.

## 2) Deploy on VM

```bash
cp infra/stacks/prefect-server/.env.example infra/stacks/prefect-server/.env
# set hostname, tunnel id, credentials filename, DB URL
# place tunnel credentials json under infra/stacks/prefect-server/.cloudflared/

./bin/project prefect up
./bin/project prefect ps
```

Remote helper flow:

```bash
./bin/remote prefect-install
./bin/remote prefect-up
./bin/remote prefect-ps
```

## 3) Cloudflare model

- Single tunnel can expose multiple hostnames (for example Prefect + MLflow).
- Keep Prefect bound to localhost on VM (`127.0.0.1:${PREFECT_BIND_PORT}`).
- Enforce Cloudflare Access app for `PREFECT_HOSTNAME`.
- Distribute Access Service Token only to trusted workers/clients.

## 4) Validation

```bash
curl -fsS "http://127.0.0.1:${PREFECT_BIND_PORT}/api/health"
./bin/project prefect logs
```

Expected external API endpoint:

`https://${PREFECT_HOSTNAME}/api`
