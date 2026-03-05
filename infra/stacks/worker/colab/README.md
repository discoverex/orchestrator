# Colab Worker Stack (Script-first)

This stack is for running a Prefect worker on Colab.

## 1) Required env

Set these before start:

- `PREFECT_API_URL`
- `PREFECT_WORK_POOL`
- `STORAGE_GATEWAY_URL`
- `STORAGE_GATEWAY_TOKEN`

## 2) Start (recommended)

```bash
PYTHONPATH=src uv run python infra/stacks/worker/colab/colab_worker_runner.py start \
  --checkpoint-dir /content/drive/MyDrive/orchestrator/checkpoints
```

## 3) Status / logs / stop

```bash
PYTHONPATH=src uv run python infra/stacks/worker/colab/colab_worker_runner.py status
PYTHONPATH=src uv run python infra/stacks/worker/colab/colab_worker_runner.py logs --tail 80
PYTHONPATH=src uv run python infra/stacks/worker/colab/colab_worker_runner.py stop
```

## Notebook (optional)

The notebook `worker_colab.ipynb` is optional convenience only.
Primary operation should use `colab_worker_runner.py`.
