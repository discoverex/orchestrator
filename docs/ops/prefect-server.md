# Prefect Server Operations

This node runs control-plane services only:

- Prefect API/UI server
- Prefect metadata Postgres (VM-local, temporary retention)
- Prefect maintenance worker (flush + prune)
- Cloudflare Tunnel sidecar

Workers stay fully separate and poll work from Prefect over HTTPS.

## 1) Data policy

- VM is not long-term SSOT.
- Completed flow runs are exported as full JSON snapshots to storage-node.
- VM retention default: `PRUNE_TTL_HOURS=72` with prune twice per day.

## 2) Deploy on VM

```bash
cp infra/stacks/prefect-server/.env.example infra/stacks/prefect-server/.env
# set hostname, tunnel id, credentials filename, DB + flush values
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

## 3) Manual maintenance commands

```bash
./bin/project prefect flush
./bin/project prefect prune
```

## 4) Cloudflare model

- Single tunnel can expose multiple hostnames (for example Prefect + MLflow).
- Keep Prefect bound to localhost on VM (`127.0.0.1:${PREFECT_BIND_PORT}`).
- Enforce Cloudflare Access app for `PREFECT_HOSTNAME`.
- Distribute Access Service Token only to trusted workers/clients.

## 5) Validation

```bash
curl -fsS "http://127.0.0.1:${PREFECT_BIND_PORT}/api/health"
./bin/project prefect logs
```

Expected external API endpoint:

`https://${PREFECT_HOSTNAME}/api`
