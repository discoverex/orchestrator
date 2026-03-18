# Local Quickstart (Dev)

This guide helps you set up a local development environment using Docker Compose.

## 1. Setup Environment

```bash
cp .env.example .env
set -a; source .env; set +a
mkdir -p "${MINIO_DATA_DIR}"
```

## 2. Build and Start Services

```bash
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml build base-runtime
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml up -d --build minio prefect worker-router worker
```

## 3. Register Deployment and Run

```bash
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect work-pool create gpu-pool --type process || true
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml run --rm register
# Default deployment target is e2e-job/e2e-test unless you override registration env.
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment run 'e2e-job/e2e-test' \
  -p job_spec_json='{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo hello-prefect"],"config":null,"inputs":{},"env":{},"outputs_prefix":null}'
```

To register an engine-owned deployment instead of the common worker-runtime default,
set `REGISTER_FLOW_SOURCE`, `REGISTER_FLOW_ENTRYPOINT`, and deployment-name env vars
for the register container before running it.

## 4. Inspect Deployment and Workers

```bash
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml exec -T -e PREFECT_API_URL=http://127.0.0.1:4200/api prefect prefect deployment ls
docker compose -p orchestrator-e2e-local -f scripts/e2e/docker-compose.local.test.yml logs worker --tail=80
```

## 5. Checkpoint Resume Support

The worker-runtime flow supports optional checkpoint resume parameters:

- `resume_key`: stable key for restart/continue
- `checkpoint_dir`: directory where step state is persisted (`<resume_key>.json`)

Example:

```bash
prefect deployment run 'e2e-job/e2e-test' \
  -p job_spec_json='{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo hello-prefect"],"config":null,"inputs":{},"env":{},"outputs_prefix":null}' \
  -p resume_key='job-001' \
  -p checkpoint_dir='/content/drive/MyDrive/orchestrator/checkpoints'
```
