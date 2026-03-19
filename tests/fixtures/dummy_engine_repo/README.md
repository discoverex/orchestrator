# Dummy Engine

This is a minimal worker-compatible dummy engine example.

It demonstrates:

- exposing an engine-owned Prefect flow callable
- reading worker-provided mount and proxy environment variables
- preparing durable files under the shared worker runtime mount
- optionally creating an MLflow run through `MLFLOW_TRACKING_URI`
- letting the worker sweep and upload staged artifacts automatically

Worker runtime contract available to engine code:

- `ORCH_WORKER_RUNTIME_DIR`
- `ORCH_CACHE_DIR`
- `PREFECT_API_URL`
- `MLFLOW_TRACKING_URI`
- `STORAGE_API_URL`

The orchestrator does not guarantee child-process access to its internal
checkpoint path or derived cache subdirectories.

## Entrypoint

```bash
python tests/fixtures/dummy_engine_repo/src/dummy_engine/main.py
```

## Flow Entrypoint

```bash
src/dummy_engine/prefect_flow.py:dummy_engine_flow
```

Default Prefect flow name:

- `dummy-engine-job`

This sample flow is intended to be deployed and executed by the engine repo
itself. The orchestrator worker only provides the shared mount contract and
local Prefect/MLflow/artifact proxy URLs.

## Artifact Staging

The engine can stage durable outputs under:

```bash
${ORCH_WORKER_RUNTIME_DIR}/engine-artifacts/<prefect-flow-run-id>/
```

Write files anywhere under that directory, then create:

```bash
${ORCH_WORKER_RUNTIME_DIR}/engine-artifacts/<prefect-flow-run-id>/_UPLOAD_READY
```

The worker-side uploader will sweep that directory and upload the staged files
plus a generated `engine-artifacts.json` manifest.

## Deployment Example

```bash
PREFECT_API_URL=https://prefect-api.discoverex.qzz.io/api \
tests/fixtures/dummy_engine_repo/scripts/register_dummy_engine_flow.sh
```

## Behavior

The engine writes:

- `scene/scene.json`
- `scene/verification.json`

And declares them in the engine artifact manifest with MLflow tag names:

- `artifact_scene_uri`
- `artifact_verification_uri`

For a real engine repo, define the deployment in that repository, then use the
worker-local mount and proxy envs at runtime instead of orchestrator-managed
runner parameters.
