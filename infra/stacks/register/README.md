# Register Node (Prefect Deployment Registration)

This profile registers Prefect deployments through a one-shot control-plane container.
Default mode creates two primary deployments and two compatibility aliases:

- fixed: `run-job/discoverex-engine-run` on queue `gpu-fixed`
- colab: `run-job/discoverex-engine-run-colab` on queue `gpu-colab`
- compat fixed alias: `run-job/engine-run`
- compat colab alias: `run-job/engine-run-colab`

## 1) Configure

```bash
cp infra/stacks/register/.env.example infra/stacks/register/.env
# edit infra/stacks/register/.env
```

## 2) Register deployment

```bash
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml exec -T prefect prefect work-pool create ${PREFECT_WORK_POOL:-gpu-pool} --type process || true
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
- Set `REGISTER_DEPLOYMENT_MODE=single` if you need backward-compatible single deployment registration.
- Set `REGISTER_FLOW_SOURCE` and `REGISTER_FLOW_ENTRYPOINT` when registering an engine-owned flow instead of the compatibility wrapper.
