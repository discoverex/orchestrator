# Runtime State Model (Prefect)

The orchestration state machine is delegated to Prefect.

## Ownership

- Scheduling/dispatch/retry/state transitions: Prefect
- Execution payload (git checkout + entrypoint): `runner`
- Artifact URL issuance and object-key policy: `storage`

## Retry Semantics

- Flow-level retry policy: `30s, 120s, 600s`
- Attempt number follows Prefect flow run count.
- Artifact prefix is attempt-scoped and immutable.

## Removed Legacy Concepts

- `worker enroll/heartbeat`
- `job poll/ack/lease`
- custom retry sweep loop
- scheduler-issued run IDs
