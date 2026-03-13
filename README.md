# Orchestrator

Prefect-based orchestration workspace with four responsibilities:

- `flows`: compatibility and maintenance Prefect workflows
- `runner`: execution adapter for source checkout + entrypoint execution
- `storage`: hexagonal storage module for presign/head control-plane logic
- `worker_router`: worker-facing auth gateway for storage control APIs and MLflow

## Documentation Map

### 1. Concepts (Understanding the System)
- [Conceptual Topology](docs/concepts/topology.md): System architecture and core interaction paths.
- [Service Flow](docs/concepts/service-flow.md): End-to-end request and data flow.
- [Auth Model](docs/concepts/auth-model.md): Authentication and security boundaries.
- [State Machine](docs/concepts/state-machine.md): Flow run states and transitions.

### 2. Guides (How-to)
- [Local Quickstart](docs/guides/quickstart-local.md): Run the full stack locally for development.
- [Colab Worker Setup](docs/guides/setup-colab-worker.md): Run a worker in Google Colab.
- [Storage Node Setup](docs/guides/setup-storage.md): Deploy the production storage node.
- [Prefect Server Setup](docs/guides/setup-prefect.md): Deploy the production Prefect server.
- [Engine Registration Checklist](docs/guides/engine-registration-checklist.md): Steps to onboard a new engine.

### 3. Contracts (Integration Specs)
- [Engine Implementation](docs/contracts/engine-implementation.md): What an engine must implement to run on this orchestrator.
- [Execution Contract](docs/contracts/execution.md): Runtime environment and execution rules.
- [Service Interface](docs/contracts/service-interface.md): API contracts between services.
- [Engine Registration](docs/contracts/registration/overview.md): Guide for external engine repositories.

### 4. Reference (Deep Dive)
- [CLI Reference](docs/reference/cli.md): Full documentation for `bin/cli`.
- [Audit Report](docs/reference/audit-report.md): CLI audit and compliance details.

## Quick Links

- **Tests**: Run `uv run pytest`
- **Lint**: Run `uv run ruff check .`
