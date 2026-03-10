# Fixed Worker Stack (Docker)

Always-on GPU worker stack for the fixed worker node.

## 1) Configure

```bash
./bin/project runtime init worker
cp infra/stacks/worker/fixed/.env.example infra/stacks/worker/fixed/.env
# edit infra/stacks/worker/fixed/.env
```

## 2) Build and start

```bash
docker compose --env-file infra/stacks/worker/fixed/.env -f infra/stacks/worker/fixed/docker-compose.yml up -d --build
```

Required worker env:

- `PREFECT_API_URL=https://<your-domain>/api`
- `PREFECT_WORK_POOL=gpu-pool`
- `PREFECT_WORK_QUEUE=gpu-fixed`
- `WORKER_ROUTER_URL=https://discoverex.qzz.io`

If Prefect is behind Cloudflare Access, also set either:

- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`

The entrypoint will merge those into `PREFECT_CLIENT_CUSTOM_HEADERS` automatically.
Storage and MLflow credentials should not be configured on workers. The worker uses the public gateway with Cloudflare Access only.

## 3) Operate

```bash
docker compose --env-file infra/stacks/worker/fixed/.env -f infra/stacks/worker/fixed/docker-compose.yml ps
docker compose --env-file infra/stacks/worker/fixed/.env -f infra/stacks/worker/fixed/docker-compose.yml logs --tail=120
docker compose --env-file infra/stacks/worker/fixed/.env -f infra/stacks/worker/fixed/docker-compose.yml down
```

Expected startup summary:

- `worker_router_url` should be populated
- Prefect custom headers should include Cloudflare keys only when Prefect itself is Access-protected

## Notes

- Default queue target is `gpu-fixed`.
- This unit is intended to be always-on and low-touch.
- Runtime data is expected outside repo at `../runtime/worker` by default.
- GitHub SSH repo URLs are normalized internally to HTTPS for resolution/cache fetches.
