# Register Node (Prefect Deployment Registration)

This profile registers Prefect deployments through a one-shot control-plane container.
Default mode registers the common worker-runtime flow and creates two primary
deployments:

- fixed: `e2e-job/e2e-test` on queue `gpu-fixed`
- colab: `e2e-job/e2e-test-colab` on queue `gpu-colab`

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
- Set `REGISTER_DEPLOYMENT_MODE=single` if you want to register one named deployment.
- Default canonical entrypoint is `src/flows/worker_runtime/flow.py:run_worker_job_flow`.
- Override `REGISTER_FLOW_SOURCE` and `REGISTER_FLOW_ENTRYPOINT` to register an engine-owned flow such as `dummy-engine-job/discoverex-engine-run`.
