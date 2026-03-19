# Orchestrator Refactor Plan

## Summary

This plan refactors the orchestrator repository around a multi-engine operating model with:

- a common Prefect worker runtime
- engine-owned Prefect deployments
- runtime repo loading through Prefect pull or Git clone
- shared worker-side artifact and MLflow handling
- no engine-specific deployment loading assumptions in the worker

The target state is:

- orchestrator no longer acts as the canonical owner of a discoverex-specific wrapper flow
- orchestrator provides the common worker runtime and control-plane support for engine deployments
- each engine can register multiple flows and branches without changing the worker runtime image
- remote e2e validates the multi-engine contract using the dummy engine fixture

## Shared Contract With Engine Repositories

This plan must stay aligned with the engine repository plan.

### Orchestrator responsibilities

- provide a common Prefect worker runtime
- load engine code from `repo_url` and `ref` at runtime
- manage repo cache, temp workdir, and runtime bootstrap
- execute engine-owned flow or declared engine entrypoint
- persist worker outputs and engine artifact uploads
- inject and preserve common MLflow tags and worker runtime metadata
- manage retries, checkpoints, and remote diagnostics

### Engine responsibilities

- own flow definitions, flow composition, and flow parameters
- own engine task DAG changes and experiments
- own engine-specific bootstrap requirements
- own engine result semantics and engine artifact manifests
- own engine-specific MLflow metrics and params

### Shared contract that must be enforced

- deployments may not require a fixed local source path on the worker
- worker runtime must support remote code loading for multiple engines
- the common artifact set is:
  - `stdout.log`
  - `stderr.log`
  - `result.json`
  - `artifacts.json`
- the common MLflow and run metadata tag set is:
  - `engine`
  - `flow_kind`
  - `branch`
  - `commit_sha`
  - `deployment_name`
  - `prefect_flow_run_id`

## Documentation Updates First

Update the docs before changing code paths.

### Files to update

- `README.md`
- `docs/contracts/execution.md`
- `docs/contracts/engine-implementation.md`
- `docs/contracts/registration/overview.md`
- `docs/contracts/service-interface.md`
- `docs/reference/cli.md`
- any quickstart or setup guide that still assumes worker-owned engine wrapper deployments

### Required documentation changes

- describe the orchestrator as a common worker and control-plane repository
- explain that engines own deployments and flow entrypoints
- remove or downgrade discoverex-specific wrapper flow language from canonical docs
- document multi-engine runtime loading behavior
- document shared artifact and MLflow contracts
- document the updated `bin/cli` command surface
- document remote e2e in terms of engine-owned deployment registration and execution

## Source Refactor In Hexagonal Terms

Refactor the code so the worker runtime is engine-agnostic and the registration path supports engine-owned deployments.

### Target separation

- domain and application layers
  - execution request semantics
  - repo loading policy
  - artifact and result contracts
  - checkpoint and retry state transitions
- inbound adapters
  - Prefect worker flow entrypoints where still needed
  - registration request parsing
  - CLI-facing use cases
- outbound adapters
  - Git and remote source loading
  - Prefect API interaction
  - storage uploads
  - MLflow proxying or tagging support
- infrastructure
  - worker container image
  - registration container and scripts
  - e2e harness and stack configuration

### Concrete refactor goals

- remove discoverex-specific ownership from the canonical execution path
- reduce `flows/engine_run` from engine wrapper semantics to common runtime semantics, or isolate it as legacy if retained
- promote repo loading and bootstrap logic into engine-agnostic execution services
- make registration support engine-owned deployments instead of wrapper-flow deployment ownership
- ensure branch and commit handling are explicit in runtime metadata
- preserve storage, checkpoint, and MLflow behavior while detaching from a single-engine assumption

### Paths expected to change

- `src/flows/engine_run/`
- `src/runner/`
- `src/deployments/register/`
- `scripts/register/`
- `scripts/ops/`
- worker image and runtime support under `infra/images/` and `infra/stacks/`

## Common Worker Runtime Changes

### Runtime expectations

- worker image keeps `uv`, `git`, Prefect, and shared helper code
- worker caches repos per engine and repo URL
- worker creates isolated temp workdirs per flow run
- worker applies bootstrap policy before flow import or entrypoint execution
- worker remains reusable across multiple engines and branches

### Execution model

- deployment declares the engine repo and flow entrypoint
- worker receives the deployment and resolves the declared code source
- worker clones or updates the target repo into cache
- worker checks out the target ref and records the executed commit SHA
- worker bootstraps dependencies and runs the declared engine flow
- worker uploads outputs, engine artifacts, and run metadata

## CLI Synchronization

The `bin/cli` surface must expose the new control-plane and worker-runtime actions directly.

### Goals

- registering engine-owned deployments must be possible without knowing internal script paths
- worker operations must remain simple
- e2e entrypoints must clearly map to the new operating model

### Required command surface

- register an engine deployment for a flow kind and branch
- inspect worker status and deployment state
- run remote validation against the dummy engine
- inspect artifact and flow-run diagnostics

### Example command family

- `bin/cli register engine --engine <engine> --flow-kind <flow-kind> --branch <branch>`
- `bin/cli worker validate-runtime`
- `bin/cli e2e remote-dummy`

The exact verbs may differ, but the top-level CLI must expose engine registration and remote validation explicitly.

## Testing And Remote E2E

### Unit and contract tests

- engine registration argument parsing
- deployment target rendering with engine, flow kind, branch, and ref
- repo loading and commit resolution services
- bootstrap policy handling
- common artifact and MLflow metadata propagation
- checkpoint behavior under the new execution model

### Integration tests

- common worker runtime executes an engine-owned deployment from remote source
- repo cache reuse works across repeated runs
- artifact upload and manifest generation remain stable
- MLflow tag injection remains consistent across engines

### Remote e2e dummy refactor

Refactor the remote dummy path so it validates the new canonical model rather than the wrapper-flow model.

#### Scope

- keep using the dummy engine fixture as a stand-in for a separate engine repository
- register the dummy engine as an engine-owned deployment
- run the dummy engine through remote code loading on the common worker
- verify completion, artifact upload, flush behavior, and MLflow metadata

#### Required updates

- update `scripts/e2e/e2e_remote_prefect_storage.sh`
- update helper scripts under `scripts/e2e/lib/`
- update any registration helper that still assumes `e2e-job/e2e-test` as the canonical deployment
- keep storage verification and prune verification intact

#### Pass criteria

- deployment registration succeeds under the new engine-owned model
- worker clones or pulls engine code successfully
- worker bootstraps and executes the dummy engine successfully
- remote verification passes for artifacts and flow completion
- MLflow verification passes for the dummy engine path where applicable

## Acceptance Criteria

- orchestrator can support multiple engines without worker image changes per engine
- engine deployments no longer rely on fixed machine-local source paths
- worker runtime remains common and engine-agnostic
- `bin/cli` exposes registration, worker, and remote e2e flows cleanly
- remote e2e dummy passes against the new canonical model

## Delivery Sequence

1. Update shared contract and operating docs.
2. Refactor registration support toward engine-owned deployments.
3. Refactor worker runtime code into engine-agnostic hexagonal boundaries.
4. Synchronize `bin/cli` with engine registration and validation operations.
5. Refactor remote dummy e2e and supporting helpers to the new model.
6. Run unit, contract, integration, and remote e2e validation for the new canonical path.
