# Colab Worker Stack (Script-first)

This stack is for running a Prefect worker on Colab.
Use this runtime layout:

- repo: Google Drive
- pip/XDG cache: Google Drive
- Python packages: current Colab interpreter (global for the VM session)

## 1) Required env

Set these before start:

- `PREFECT_API_URL`
- `PREFECT_WORK_POOL` (recommended: `gpu-pool`)
- `PREFECT_WORK_QUEUE` (recommended: `gpu-colab`)
- `STORAGE_GATEWAY_URL`
- `STORAGE_GATEWAY_TOKEN`
- If Prefect is behind Cloudflare Access, also set either:
  - `PREFECT_CF_ACCESS_CLIENT_ID` / `PREFECT_CF_ACCESS_CLIENT_SECRET`
  - or `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET`

## 2) Bootstrap (recommended first step)

```bash
PYTHONPATH=src python infra/stacks/worker/colab/colab_worker_runner.py bootstrap \
  --repo-dir /content/drive/MyDrive/discoverex/orchestrator \
  --cache-root /content/drive/MyDrive/discoverex/cache
```

This upgrades `pip/setuptools/wheel` in the current Colab interpreter and installs
the project in editable mode with:

- `--no-build-isolation`
- `--use-feature=fast-deps`

The pip and resolver cache is reused from Drive through:

- `PIP_CACHE_DIR=/content/drive/MyDrive/discoverex/cache/pip`
- `XDG_CACHE_HOME=/content/drive/MyDrive/discoverex/cache/xdg`

## 3) Start worker

```bash
python infra/stacks/worker/colab/colab_worker_runner.py start \
  --skip-install \
  --checkpoint-dir /content/drive/MyDrive/orchestrator/checkpoints
```

`start` auto-loads repo-root `.env` when present, creates the checkpoint directory
after Google Drive is mounted, and assumes bootstrap already installed Prefect into
the current interpreter. When Cloudflare Access env vars are present, it also exports
`PREFECT_CLIENT_CUSTOM_HEADERS` automatically for Prefect CLI/worker requests.

## 4) Status / logs / stop

```bash
python infra/stacks/worker/colab/colab_worker_runner.py status
python infra/stacks/worker/colab/colab_worker_runner.py logs --tail 80
python infra/stacks/worker/colab/colab_worker_runner.py stop
```

## Notebook (optional)

The notebook `worker_colab.ipynb` is optional convenience only.
Primary operation should use `colab_worker_runner.py`.
The notebook keeps only the minimum bootstrap logic inline. It can start from a
state where only the notebook file exists, configure runtime env, clone or
refresh the repository into Google Drive, and then invoke the checked-out
`colab_worker_runner.py` for bootstrap and worker lifecycle. Colab output shows
step-by-step progress logs for each stage.
