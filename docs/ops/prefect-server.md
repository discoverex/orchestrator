# Prefect Server Operations

This node runs control-plane services only:

- Prefect API/UI server
- Prefect metadata Postgres (VM-local, temporary retention)
- Prefect maintenance worker (flush + prune)

Workers stay fully separate and poll work from Prefect over HTTPS.

## 1) Data policy

- VM is not long-term SSOT.
- Completed flow runs are exported as full JSON snapshots to storage-node.
- VM retention default: `PRUNE_TTL_HOURS=72` with prune twice per day.

## 2) Deploy on VM

```bash
cp infra/stacks/prefect-server/.env.example infra/stacks/prefect-server/.env
# set PREFECT_SERVER_IMAGE + API URL + DB + flush values

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

## 4) Network model

- Route Prefect domain with DNS A record to VM public IP.
- Set `PREFECT_API_PUBLIC_URL` to external endpoint (`https://<domain>/api`).
- Keep `PREFECT_BIND_ADDRESS=127.0.0.1` if reverse proxy terminates TLS on same VM.
- If exposing Prefect container port directly, set `PREFECT_BIND_ADDRESS=0.0.0.0` and apply firewall allowlist.
- If Cloudflare Access is used, distribute service token only to trusted workers/clients.

## 5) Validation

```bash
curl -fsS "http://127.0.0.1:${PREFECT_BIND_PORT}/api/health"
./bin/project prefect logs
```

Expected external API endpoint:

`https://<domain>/api`

## 6) Remote chain validation (register -> run -> storage -> flush/prune)

Run from the storage-node machine:

```bash
./bin/project e2e-remote \
  --prefect-api-url https://<domain>/api
```

PoC-only destructive prune verification:

```bash
./bin/project e2e-remote \
  --prefect-api-url https://<domain>/api \
  --prune-mode apply \
  --prune-ttl-hours 0
```

Operational notes:

- `register` is a one-shot container (`run --rm`) that exits after deployment registration.
- The validation script assumes production worker is already polling the target pool/queue.
- `--bootstrap-worker` exists only as temporary bootstrap support and should be removed when production worker validation is fully adopted.
