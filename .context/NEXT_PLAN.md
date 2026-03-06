# NEXT PLAN - Fixed GPU + Colab GPU Worker Operating Units

## Objective
- Complete two production operating units:
  - Fixed worker: one always-on Docker GPU worker.
  - Colab workers: notebook-based burst GPU workers.
- Keep routing policy explicit:
  - fixed-first default,
  - burst to Colab when backlog exists,
  - optional colab-first mode,
  - strict priority mode (wait until preferred queue is empty).

## Operating Model
- Work pool: `gpu-pool` (process worker type).
- Work queues:
  - `gpu-fixed` (fixed Docker worker),
  - `gpu-colab` (Colab workers).
- Deployments:
  - `engine-run/engine-run` -> fixed queue (compatibility default),
  - `engine-run/engine-run-colab` -> colab queue.

## Implementation Scope
1. Fixed worker stack:
   - Add `infra/stacks/worker/fixed/` (`docker-compose.yml`, `.env.example`, `README.md`).
2. Worker entrypoint:
   - Add `PREFECT_WORK_QUEUE` support (`--work-queue`).
3. Register path:
   - Extend register to create fixed + colab deployments in one run.
   - Keep single-deployment compatibility options.
4. Colab path:
   - Replace uv-first flow with pip-minimal bootstrap.
   - Add `requirements-colab.txt`.
   - Keep notebook operation script-first.
5. Router:
   - Add `scripts/ops/prefect_submit_router.py` to select deployment by queue depth and mode.
6. CLI:
   - Extend `bin/project` with worker unit commands and submit router wrapper.

## Validation
- Unit tests:
  - deployment registration behavior (dual + compatibility),
  - router decision behavior.
- Command checks:
  - Python compile for changed scripts/modules.
- E2E target:
  - fixed queue run completion,
  - storage artifact persistence,
  - flush/prune checks.

## Acceptance Criteria
- Fixed worker can run independently through Docker stack commands.
- Colab runner starts without uv dependency and uses minimal pip bootstrap.
- Register command creates both fixed and colab deployments by default.
- Router can enforce fixed-first/colab-first/strict-priority.
- Existing `engine-run/engine-run` flow remains runnable.
