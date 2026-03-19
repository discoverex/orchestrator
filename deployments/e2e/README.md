# E2E Deployment Spec

This directory is the declarative source of truth for canonical E2E deployment
naming.

- flow code: `src/flows/worker_runtime/flow.py:run_worker_job_flow`
- canonical flow name: `e2e-job`
- canonical deployments:
  - `e2e-job/e2e-test`
  - `e2e-job/e2e-test-colab`

Current status:

- registration defaults now read `deployments/e2e/e2e-deployments.yaml`
- CLI or env overrides remain available for one-off registration changes
- env-sensitive values such as `PREFECT_API_URL`, auth headers, and source root
  stay outside the YAML

Document scope:

- keep only flow and deployment naming and queue selection here
- keep runtime-specific env vars, auth, and storage endpoints in compose or env files
