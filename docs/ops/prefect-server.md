# Prefect Server Operations

This node runs control-plane services only:

- Prefect API/UI server
- Prefect metadata Postgres (VM-local, temporary retention)
- Prefect maintenance worker (flush + prune)

Workers stay fully separate and poll work from Prefect over HTTPS.

Related design docs:

- [Service Flow](/home/esillileu/discoverex/orchestrator/docs/dev/service-flow.md)
- [Service Auth Model](/home/esillileu/discoverex/orchestrator/docs/dev/service-auth-model.md)
- [Service Contracts](/home/esillileu/discoverex/orchestrator/docs/dev/service-contracts.md)
- [Engine Prefect Registration](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/README.md)

## 1) Data policy

- VM is not long-term SSOT.
- Completed flow runs are exported as full JSON snapshots to storage-node.
- VM retention default: `PRUNE_TTL_HOURS=72` with prune twice per day.

## 2) Deploy on VM

```bash
cp infra/stacks/prefect-server/.env.example infra/stacks/prefect-server/.env
# set PREFECT_SERVER_IMAGE + API URL + DB + flush values

./bin/cli prefect up
./bin/cli prefect ps
```

Remote helper flow:

```bash
./bin/cli prefect install --remote
./bin/cli prefect up --remote
./bin/cli prefect ps --remote
./bin/cli prefect workers --remote
```

## 3) Manual maintenance commands

```bash
./bin/cli prefect flush
./bin/cli prefect prune
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
./bin/cli prefect logs
```

Expected external API endpoint:

`https://<domain>/api`

## 6) Remote chain validation (register -> run -> storage -> flush/prune)

Run from the storage-node machine:

```bash
./bin/cli e2e remote dummy \
  --prefect-api-url https://<domain>/api
```

Full engine validation:

```bash
./bin/cli e2e remote engine \
  --prefect-api-url https://<domain>/api
```

PoC-only destructive prune verification:

```bash
./bin/cli e2e remote engine \
  --prefect-api-url https://<domain>/api \
  --prune-mode apply \
  --prune-ttl-hours 0
```

Operational notes:

- `register` is a one-shot container (`run --rm`) that exits after deployment registration.
- `remote dummy` is the control-plane check and avoids external engine helper dependencies.
- `remote engine` is the full production path and assumes the external engine helper + repo inputs are available.
- The validation scripts assume production worker is already polling the target pool/queue.
- `--bootstrap-worker` exists only as temporary bootstrap support and should be removed when production worker validation is fully adopted.
- Recommended production split:
  - fixed worker: `gpu-pool` + `gpu-fixed`
  - colab workers: `gpu-pool` + `gpu-colab`
