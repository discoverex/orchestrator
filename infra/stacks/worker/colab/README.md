# Colab Worker Stack (Script-first)

This stack is for running a Prefect worker on Colab.
It uses pip-minimal bootstrap and keeps Colab base dependencies intact.

## 1) Required env

Set these before start:

- `PREFECT_API_URL`
- `PREFECT_WORK_POOL` (recommended: `gpu-pool`)
- `PREFECT_WORK_QUEUE` (recommended: `gpu-colab`)
- `STORAGE_GATEWAY_URL`
- `STORAGE_GATEWAY_TOKEN`

## 2) Start (recommended)

```bash
PYTHONPATH=src python infra/stacks/worker/colab/colab_worker_runner.py start \
  --checkpoint-dir /content/drive/MyDrive/orchestrator/checkpoints
```

`colab_worker_runner.py` installs `infra/stacks/worker/colab/requirements-colab.txt`
only when compatible Prefect is not already installed.

## 3) Status / logs / stop

```bash
PYTHONPATH=src python infra/stacks/worker/colab/colab_worker_runner.py status
PYTHONPATH=src python infra/stacks/worker/colab/colab_worker_runner.py logs --tail 80
PYTHONPATH=src python infra/stacks/worker/colab/colab_worker_runner.py stop
```

## Notebook (optional)

The notebook `worker_colab.ipynb` is optional convenience only.
Primary operation should use `colab_worker_runner.py`.
