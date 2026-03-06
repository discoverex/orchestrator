# Phase 4 - Documentation Refresh

## Goal
현재 구현과 운영절차를 문서로 일치시킨다.

## In Scope
- `README.md`
- `docs/ops/storage-node.md`
- `docs/ops/prefect-server.md`
- `docs/dev/execution-contract.md`
- `docs/dev/state-machine.md`

## Required Content
1. System conceptual map (components + responsibilities)
2. Interaction points (API paths, queues, storage URIs)
3. Auth model (CF Access, gateway token, Prefect API)
4. Node-specific setup/run/check steps
5. Minimal end-to-end validation flow

## Mandatory Removals
- Explorer routes/env/config references must be deleted.
- Replace with supported operator workflows (storage-gateway API, MinIO console route).

## Documentation Quality Bar
- Every command copy-pastable.
- Every env var traced to file/path.
- Each runbook includes failure symptom + immediate checks.

## Exit Criteria
- Docs are consistent with final code paths and interfaces.
- New operator can bootstrap with docs only.
