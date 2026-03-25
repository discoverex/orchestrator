# `bin/cli` Reference

`bin/cli` is the canonical internal operator entrypoint for this repository.
Run it from the repository root:

```bash
./bin/cli <domain> <action> [options]
```

Top-level help:

```bash
./bin/cli --help
```

## 1) Runtime and path conventions

- Repo root is assumed to be `orchestrator`.
- Repo-level `.env` is auto-loaded by shared shell helpers when present.
- Default runtime root is `../runtime` unless `RUNTIME_ROOT` is overridden.
- Compose-backed domains use fixed stack files:
  - local: `scripts/e2e/docker-compose.local.test.yml`
  - storage: `infra/stacks/storage-node/docker-compose.yml`
  - register: `infra/stacks/register/docker-compose.yml`
  - worker fixed: `infra/stacks/worker/fixed/docker-compose.yml`
  - prefect: `infra/stacks/prefect-server/docker-compose.yml`

## 2) Domains at a glance

```bash
./bin/cli base build [docker build args...]
./bin/cli runtime init [storage|worker|all]
./bin/cli storage <up|down|ps|logs|build> [args...]
./bin/cli local <up|down|ps|logs|build> [args...]
./bin/cli register <run|build> [args...]
./bin/cli worker fixed <up|down|ps|logs|build> [args...]
./bin/cli worker register-gpu [args...]
./bin/cli worker submit [router args...]
./bin/cli observability <workers|fixed-dummy-smoke> [args...]
./bin/cli prefect <up|down|ps|logs|build|flush|prune|install|workers> [--remote] [args...]
./bin/cli e2e local [core|mlflow|priority] [--keep-on-fail] [--timeout-sec N]
./bin/cli e2e remote [engine] [--prefect-api-url URL] [--work-pool NAME] [--work-queue NAME] [--prune-mode dry-run|apply] [--bootstrap-worker] [--timeout-sec N]
./bin/cli e2e remote dummy [--prefect-api-url URL] [--work-pool NAME] [--work-queue NAME] [--prune-mode dry-run|apply] [--bootstrap-worker] [--timeout-sec N]
./bin/cli ops <connect|postgres|dump|ci> [args...]
```

이 문서는 실제 `bin/cli`와 각 `scripts/*/cli.sh` usage를 기준으로 유지한다.
운영 배경이나 감사 결과는 별도 문서로 두지 않는다.

## 3) Domain reference

### `base`

Build the shared base image used by compose stacks.

```bash
./bin/cli base build
./bin/cli base build --no-cache
```

Implementation note:

- builds `infra/images/base.Dockerfile`
- tags image as `orchestrator-base:local`

### `runtime`

Prepare runtime directories outside the repo.

```bash
./bin/cli runtime init storage
./bin/cli runtime init worker
./bin/cli runtime init all
```

Created directories:

- `storage`: `../runtime/storage/data/minio`, `../runtime/storage/data/mlflow-db`, `../runtime/storage/backup`, `../runtime/storage/logs`
- `worker`: `../runtime/worker/checkpoints`, `../runtime/worker/cache`, `../runtime/worker/logs`

### `storage`

Manage the storage-node compose stack.

```bash
./bin/cli storage up
./bin/cli storage ps
./bin/cli storage logs
./bin/cli storage down
./bin/cli storage build
```

Behavior:

- uses `infra/stacks/storage-node/.env` as compose env file when present
- `build` first builds the shared base image, then builds `base-runtime`, `worker-router`, and `mlflow`
- `logs` defaults to `--tail=120`

Related runbook:

- [setup-storage.md](../guides/setup-storage.md)

### `local`

Manage the local all-in-one validation stack used for dev and E2E.

```bash
./bin/cli local up
./bin/cli local ps
./bin/cli local logs
./bin/cli local down
./bin/cli local build
```

Behavior:

- uses `scripts/e2e/docker-compose.local.test.yml`
- `build` first builds the shared base image, then builds `base-runtime`, `worker-router`, the local CPU worker image, and `register`
- local `worker` uses `infra/images/worker-cpu.Dockerfile` and is tagged `orchestrator-worker-cpu:local`
- `logs` defaults to `--tail=120`

### `register`

Build or run the deployment registration container.

```bash
./bin/cli register build
./bin/cli register run
```

Behavior:

- uses `infra/stacks/register/.env` and `infra/stacks/register/docker-compose.yml`
- `run` executes `docker compose run --rm register`
- `build` builds the shared base image first
- default registration spec is `deployments/e2e/e2e-deployments.yaml`
- default registration entrypoint is `src/flows/worker_runtime/flow.py:run_worker_job_flow`

### `worker`

Worker-related commands are split into fixed worker lifecycle, deployment registration, and routed submission.

Fixed worker:

```bash
./bin/cli worker fixed up
./bin/cli worker fixed ps
./bin/cli worker fixed logs
./bin/cli worker fixed down
./bin/cli worker fixed build
```

Behavior:

- uses `infra/stacks/worker/fixed/.env` and `infra/stacks/worker/fixed/docker-compose.yml`
- host `../runtime/worker` is mounted to `/var/lib/orchestrator`
- `up` runs `scripts/ops/install_nvidia_container_toolkit.sh`, ensures runtime directories via `runtime init worker`, and requires elevated privileges to assign worker runtime ownership to UID 10001 before `docker compose up -d --build`
- `build` only builds the standalone GPU worker image

CPU smoke worker:

```bash
docker compose --env-file infra/stacks/worker/fixed/.env.cpu-test -f infra/stacks/worker/fixed/docker-compose.cpu-test.yml up -d --build
```

Behavior:

- uses `infra/images/worker-cpu.Dockerfile`
- tags image as `orchestrator-worker-cpu:local`

Deployment registration shortcut:

```bash
./bin/cli worker register-gpu
```

Behavior:

- currently routes to the same one-shot register container as `./bin/cli register run`

Routed submission:

```bash
./bin/cli worker submit --job-spec-json '{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo hello"]}'
./bin/cli worker submit --job-spec-file /tmp/job.json
```

Important options:

- `--mode fixed-first|colab-first`
- `--strict-priority true|false`
- `--queue-depth-threshold N`
- `--divert-when-running true|false`
- `--fixed-deployment NAME`
- `--colab-deployment NAME`
- `--fixed-queue NAME`
- `--colab-queue NAME`
- `--job-spec-json JSON`
- `--job-spec-file PATH`
- `--resume-key KEY`
- `--checkpoint-dir PATH`
- `--parameters-json JSON`

Behavior:

- implemented by `scripts/ops/prefect_submit_router.py`
- selects a deployment based on fixed/colab queue depth policy
- creates a Prefect flow run and prints JSON result including selected deployment and flow run id

### `observability`

Prefect inspection and smoke-check helpers.

List workers in a pool:

```bash
./bin/cli observability workers
./bin/cli observability workers --work-pool gpu-pool --limit 50
```

Options:

- `--work-pool` default `gpu-pool`
- `--limit` default `20`
- `--env-file` optional env file for Prefect API settings

Run fixed dummy smoke:

```bash
./bin/cli observability fixed-dummy-smoke
./bin/cli observability fixed-dummy-smoke --deployment-name my-flow/my-deployment
```

Options:

- `--deployment-name` default `e2e-job/e2e-test`
- `--env-file` optional env file for Prefect API settings

Behavior:

- creates a flow run with inline fixed-dummy job spec
- default target is the standard worker-runtime deployment FQN `e2e-job/e2e-test`
- prints JSON response for the created run

### `prefect`

Manage the Prefect server stack locally or on the remote VM.

Local stack:

```bash
./bin/cli prefect build
./bin/cli prefect up
./bin/cli prefect ps
./bin/cli prefect logs
./bin/cli prefect down
```

Maintenance:

```bash
./bin/cli prefect flush
./bin/cli prefect prune
./bin/cli prefect flush --remote
./bin/cli prefect prune --remote
```

Remote VM:

```bash
./bin/cli prefect install --remote
./bin/cli prefect up --remote
./bin/cli prefect ps --remote
./bin/cli prefect logs --remote
./bin/cli prefect workers --remote
```

Behavior:

- local compose uses `infra/stacks/prefect-server/.env` and `infra/stacks/prefect-server/docker-compose.yml`
- local `build` builds both `orchestrator-base:local` and `orchestrator-prefect-server:local`
- `flush` runs `prefect_flush_completed.py --once`
- `prune` runs `prefect_prune_completed.py --apply`
- `flush` and `prune` honor `--remote` and execute via the remote Prefect compose stack
- `workers --remote` queries worker lists from pools defined by `REMOTE_WORKER_POOLS` or defaults to `gpu-pool`
- `install --remote` bootstraps the VM from the repo checkout via `scripts/ops/prefect_vm_bootstrap.sh`

Remote env requirements:

- `REMOTE_USERNAME`
- `REMOTE_HOST`
- `GITHUB_DEPLOY_KEY_PATH`

Remote defaults:

- `REMOTE_PREFECT_PATH=/opt/services/orchestrator-prefect`
- `REMOTE_PREFECT_ENV=.env`
- `REMOTE_PREFECT_COMPOSE=docker-compose.yml`
- `REMOTE_PROJECT_PATH=/home/<REMOTE_USERNAME>/discoverex/orchestrator` when not explicitly set

Related runbook:

- [setup-prefect.md](../guides/setup-prefect.md)

### `e2e`

Run end-to-end validation flows.

Local:

```bash
./bin/cli e2e local
./bin/cli e2e local core
./bin/cli e2e local mlflow --keep-on-fail --timeout-sec 240
```

Behavior:

- default local mode is `core`
- routes to `scripts/e2e/e2e_local_orchestrator.sh --mode <core|mlflow>`

Remote:

```bash
./bin/cli e2e remote --prefect-api-url https://prefect.example.com/api
./bin/cli e2e remote engine --prefect-api-url https://prefect.example.com/api --prune-mode dry-run
./bin/cli e2e remote dummy --prefect-api-url https://prefect.example.com/api
```

Behavior:

- default remote mode is `engine`
- routes to `scripts/e2e/e2e_remote_prefect_storage.sh`
- performs authenticated health checks against `STORAGE_API_URL` using Cloudflare Access headers
- when `--prefect-api-url` is omitted, repo `.env` value is used if present
- when mode is `dummy`, `scripts/e2e/fixed_dummy_inline_job.json` is injected automatically
- when `--prune-mode` is omitted, `dry-run` is applied automatically
- `--mlflow-s3-endpoint-url` can be used to override the S3 endpoint for remote artifact verification

### `ops`

Direct operational helpers for the remote environment and local CI checks.

```bash
./bin/cli ops connect
./bin/cli ops postgres
./bin/cli ops dump
./bin/cli ops ci
```

Behavior:

- `connect`: SSH into `${REMOTE_USERNAME}@${REMOTE_HOST}` using `GITHUB_DEPLOY_KEY_PATH`
- `postgres`: open remote Postgres shell with `docker exec -it postgres psql -U gtrpgm -d gtrpgm`
- `dump`: stream remote `pg_dump` into `dump_YYYYMMDD_HHMMSS.sql` in the current local directory
- `ci`: runs `uvx ruff check --fix .`, `uvx ruff format .`, `uv run mypy`, `uv run pytest -q`

## 4) Common examples

```bash
./bin/cli runtime init all
./bin/cli storage up
./bin/cli local up
./bin/cli register run
./bin/cli worker fixed up
./bin/cli observability workers --work-pool gpu-pool
./bin/cli prefect up
./bin/cli prefect ps --remote
./bin/cli e2e local mlflow --keep-on-fail
./bin/cli e2e remote dummy --prefect-api-url https://prefect.example.com/api
./bin/cli ops connect
```

## 5) Related documents

- [README.md](../../README.md)
- [setup-prefect.md](../guides/setup-prefect.md)
- [setup-storage.md](../guides/setup-storage.md)
