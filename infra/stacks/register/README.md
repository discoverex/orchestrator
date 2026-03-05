# Register Node (Prefect Deployment Registration)

This profile registers `engine_run_flow` deployment through a one-shot container.

## 1) Configure

```bash
cp infra/stacks/register/.env.example infra/stacks/register/.env
# edit infra/stacks/register/.env
```

## 2) Register deployment

```bash
docker compose -f docker-compose.local.yml exec -T prefect prefect work-pool create ${PREFECT_WORK_POOL:-colab-gpu} --type process || true
docker compose --env-file infra/stacks/register/.env -f infra/stacks/register/docker-compose.yml build base-runtime
docker compose --env-file infra/stacks/register/.env -f infra/stacks/register/docker-compose.yml run --rm register
```

## 3) Verify (optional)

```bash
prefect deployment ls
```

## Notes

- This container is intended for one-shot registration, not a long-running worker.
- On low-memory hosts (~1 GB RAM), registration is usually feasible, but avoid running heavy worker workloads on the same node.
