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

## 3) Operate

```bash
docker compose --env-file infra/stacks/worker/fixed/.env -f infra/stacks/worker/fixed/docker-compose.yml ps
docker compose --env-file infra/stacks/worker/fixed/.env -f infra/stacks/worker/fixed/docker-compose.yml logs --tail=120
docker compose --env-file infra/stacks/worker/fixed/.env -f infra/stacks/worker/fixed/docker-compose.yml down
```

## Notes

- Default queue target is `gpu-fixed`.
- This unit is intended to be always-on and low-touch.
- Runtime data is expected outside repo at `../runtime/worker` by default.
