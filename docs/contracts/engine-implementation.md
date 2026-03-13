# Engine Implementation Contract

This document defines what an engine implementation must assume and provide
when it is executed by an orchestrator worker.

## 1) Scope

The worker is responsible for:

- resolving the requested code version
- preparing the working directory
- injecting runtime environment variables
- capturing `stdout`, `stderr`, and `result.json`
- requesting presigned artifact URLs
- uploading artifacts to object storage

The engine entrypoint is responsible for:

- starting non-interactively
- reading only the contract inputs it needs
- returning a meaningful exit code
- optionally recording metadata to MLflow

The engine must not assume direct access to MinIO credentials or internal
storage services.

## 2) Job Spec Contract

The worker receives a `job_spec_json` payload and validates it against
[job_spec.py](/home/esillileu/discoverex/orchestrator/src/flows/job_spec.py).

Required fields:

- `engine: str`
- `entrypoint: list[str]`

Mode-dependent fields:

- `run_mode=repo`
  - `repo_url: str`
  - `ref: str`
- `run_mode=inline`
  - `repo_url` must be omitted
  - `ref` must be omitted
  - `config` must be omitted

Optional fields:

- `config: str | None`
- `job_name: str | None`
- `inputs: dict[str, Any]`
- `env: dict[str, str]`
- `outputs_prefix: str | None`

Rules:

- `entrypoint` must be non-empty.
- `config` must be repository-relative and must not escape the repo root.
- `engine` should be present in `infra/engines/registry.json` when that registry is used.

## 3) Worker-to-Engine Runtime Contract

Before launching the engine process, the worker injects these variables:

- `ORCH_ENGINE`
- `ORCH_RUN_MODE`
- `ORCH_FLOW_RUN_ID`
- `ORCH_ATTEMPT`
- `ORCH_OUTPUTS_PREFIX`
- `ORCH_RESOLVED_COMMIT`
- `ORCH_JOB_INPUTS_JSON`

Conditionally injected:

- `ORCH_JOB_NAME`
- `ORCH_JOB_CONFIG_PATH`

The engine may also receive additional variables from `job_spec.env`.

Source: [git_runner.py](/home/esillileu/discoverex/orchestrator/src/runner/git_runner.py)

## 4) Execution Rules

The engine entrypoint must satisfy these rules:

- It must run without interactive input.
- It must terminate on its own.
- It must use the process exit code to report success or failure.
- It must write meaningful diagnostic information to `stdout` and `stderr`.
- It must tolerate execution from a temporary working directory.

If the engine is in `repo` mode:

- the repository must be cloneable by the worker
- the requested `ref` must resolve successfully
- the repository must contain everything needed for execution

## 5) Dependency Model

For `repo` mode, the worker may prepare a per-repo environment automatically:

- if `pyproject.toml` exists, the worker runs `uv sync`
- if `uv.lock` exists, the worker runs `uv sync --frozen`

That means the recommended repo shape for an engine is:

- `pyproject.toml`
- `uv.lock`
- deterministic entrypoint command

If the engine needs system packages, GPU libraries, CUDA, or other host-level
dependencies, those must already exist on the worker image or worker node.
The orchestrator does not provision OS packages during a run.

## 6) Storage Contract

The engine must not upload orchestration artifacts directly.

The worker captures and uploads:

- `stdout.log`
- `stderr.log`
- `result.json`
- `artifacts.json`

Artifact object layout:

- `jobs/{flow_run_id}/attempt-{attempt}/stdout.log`
- `jobs/{flow_run_id}/attempt-{attempt}/stderr.log`
- `jobs/{flow_run_id}/attempt-{attempt}/result.json`
- `jobs/{flow_run_id}/attempt-{attempt}/artifacts.json`

The worker is the only component that should use:

- `STORAGE_API_URL`
- presigned artifact PUT URLs

The engine should treat artifact persistence as an orchestrator concern.

## 7) MLflow Contract

If the engine needs MLflow, it should use only the tracking URI exposed to it.

Expected worker-facing URI:

- `MLFLOW_TRACKING_URI=https://storage-api.discoverex.qzz.io/mlflow`

Rules:

- use MLflow for params, metrics, tags, status, and run metadata
- do not assume direct access to the MLflow backend container
- do not assume direct access to MinIO credentials
- prefer storing object references such as `s3://...` URIs in MLflow tags rather than uploading artifacts through MLflow

When the tracking URI is remote HTTP(S) and Cloudflare Access credentials are
present, the worker starts a local proxy and rewrites `MLFLOW_TRACKING_URI`
for the child process. The engine does not need to know about this proxy.

Source: [mlflow_proxy.py](/home/esillileu/discoverex/orchestrator/src/runner/mlflow_proxy.py)

## 8) Output Expectations

The worker always writes a `result.json` with at least:

- `exit_code`
- `resolved_commit`
- `run_mode`
- `entrypoint`

If an engine wants richer machine-readable output, the simplest pattern is:

- write structured JSON to `stdout`, or
- write additional files inside the workdir and emit their references through `stdout`

The standard smoke job currently validates:

- artifact upload to object storage
- MLflow run creation
- MLflow tag persistence

Reference job:
[fixed_dummy_inline_job.json](/home/esillileu/discoverex/orchestrator/scripts/e2e/fixed_dummy_inline_job.json)

## 9) Worker Environment Requirements

An engine implementation can assume the worker node already has:

- a reachable `PREFECT_API_URL`
- a reachable `STORAGE_API_URL`
- working DNS for public service hosts
- writable checkpoint storage

For GPU engines, the worker node must additionally have:

- working GPU runtime on the host
- the required driver/runtime stack already installed
- a worker image compatible with the engine's framework stack

The orchestrator does not infer or install framework-specific GPU dependencies.

## 10) Acceptance Checklist

An engine implementation is considered contract-compliant if:

1. `job_spec_json` validates successfully.
2. The entrypoint starts and exits non-interactively.
3. The flow run reaches `COMPLETED` when the engine succeeds.
4. `stdout.log`, `stderr.log`, `result.json`, and `artifacts.json` are uploaded.
5. If MLflow is used, the engine can create and read back an MLflow run through the provided tracking URI.

## 11) Recommended Validation

Use the standard smoke path first:

```bash
# Default deployment is e2e-job/e2e-test
./bin/cli observability fixed-dummy-smoke --timeout-sec 240

# Or specify a custom deployment name
./bin/cli observability fixed-dummy-smoke --deployment-name my-custom-flow/my-deployment --timeout-sec 240

uv run python scripts/observability/prefect_verify_standard_dummy_run.py --flow-run-id <FLOW_RUN_ID>
```

For repository-backed engines, follow with a repo-mode validation using the
actual engine repository and a minimal entrypoint.
