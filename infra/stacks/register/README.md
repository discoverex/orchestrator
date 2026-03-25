# Register Node (Prefect Deployment Registration)

이 스택은 one-shot registration container를 실행해 Prefect deployment를 등록한다.
배포 이름의 정식 기준은 [deployments/e2e/README.md](../../../deployments/e2e/README.md)와
[deployments/e2e/e2e-deployments.yaml](../../../deployments/e2e/e2e-deployments.yaml)이다.

현재 기본 등록은 common worker-runtime flow를 사용하며, canonical deployment 둘과
코드에 남아 있는 compat alias를 함께 만들 수 있다.

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
- Default canonical entrypoint is `src/flows/worker_runtime/flow.py:run_worker_job_flow`.
- Override `REGISTER_FLOW_SOURCE` and `REGISTER_FLOW_ENTRYPOINT` to register an engine-owned flow such as `dummy-engine-job/discoverex-engine-run`.
