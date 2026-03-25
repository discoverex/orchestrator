# Conceptual Topology

배경과 문제 정의는 [problem-statement.md](problem-statement.md)를 따른다. 이 문서는
현재 시스템의 노드 분리와 책임 배치를 설명한다.

- **Prefect server node**:
  - Prefect API/UI + metadata DB
  - deployment registration + orchestration state
- **Worker nodes**:
  - fixed docker worker (`gpu-fixed`)
  - optional colab workers (`gpu-colab`)
- **Storage node**:
  - MinIO + worker-router + MLflow
  - artifact/object persistence and worker-facing auth/presign routing

## Core Interaction Path

1. Register deployment to Prefect.
2. Submit flow run to work pool/queue.
3. Worker executes the registered common worker-runtime flow or engine-owned flow.
4. Worker requests presigned URLs via `storage-api` and uploads objects through `storage-api` signed object paths.
5. Worker records run metadata via `storage-api/mlflow`.
6. Flush exports completed run snapshots to storage.
7. Prune handles retention (optional apply mode).

## Standard Validation Path

1. Run the standard Prefect dummy smoke.
2. By default it targets `e2e-job/e2e-test`, but any flow/deployment FQN is allowed.
2. Verify artifact objects and MLflow linkage.

```bash
# Default deployment target
./bin/cli observability fixed-dummy-smoke --timeout-sec 240

# Custom deployment target
./bin/cli observability fixed-dummy-smoke --deployment-name my-flow/my-test --timeout-sec 240

uv run python scripts/observability/prefect_verify_standard_dummy_run.py --flow-run-id <FLOW_RUN_ID>
```
