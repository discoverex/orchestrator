# Dummy Engine

This is a minimal worker-compatible dummy engine example.

It demonstrates:

- exposing a deployable Prefect flow callable
- reading worker-injected environment variables
- parsing `ORCH_JOB_INPUTS_JSON`
- writing durable output files under `ORCH_ENGINE_ARTIFACT_DIR`
- writing `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- optionally creating an MLflow run through `MLFLOW_TRACKING_URI`
- printing structured JSON to `stdout`

Worker runtime parent dirs available to engine code:

- `ORCH_WORKER_RUNTIME_DIR`
- `ORCH_CACHE_DIR`

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

This sample flow is intended to be loaded by the orchestrator runner as a
Prefect subflow:

- `src/dummy_engine/prefect_flow.py:dummy_engine_flow`

and delegates execution to the common worker runtime flow.

## Register Example

```bash
PREFECT_API_URL=https://prefect-api.discoverex.qzz.io/api \
tests/fixtures/dummy_engine_repo/scripts/register_dummy_engine_flow.sh
```

You can also register it through the existing register stack by setting:

```bash
REGISTER_FLOW_SOURCE=/app
REGISTER_FLOW_ENTRYPOINT=tests/fixtures/dummy_engine_repo/src/dummy_engine/prefect_flow.py:dummy_engine_flow
```

## Behavior

The engine writes:

- `scene/scene.json`
- `scene/verification.json`

And declares them in the engine artifact manifest with MLflow tag names:

- `artifact_scene_uri`
- `artifact_verification_uri`

## Repo-mode parameters example

Use the current repository as the `repo_url` when testing locally:

```json
{
  "run_mode": "repo",
  "engine": "dummy-engine",
  "repo_url": "/path/to/orchestrator",
  "ref": "main",
  "flow_entrypoint": "src/dummy_engine/prefect_flow.py:dummy_engine_flow",
  "job_name": "dummy-engine-smoke",
  "inputs": {
    "scene_id": "dummy-scene",
    "version_id": "v1"
  },
  "env": {
    "MLFLOW_TRACKING_URI": "https://storage-api.discoverex.qzz.io/mlflow"
  },
  "outputs_prefix": null
}
```

For a real external engine repo, copy this example into that repository and
replace the `repo_url`, `ref`, and `flow_entrypoint` as needed.
