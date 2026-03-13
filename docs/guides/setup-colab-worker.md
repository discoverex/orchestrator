# Colab Worker Setup

This guide covers setting up a worker in a Google Colab environment.

## 1. Bootstrap

Primary operation should be script-first:

```bash
PYTHONPATH=src python infra/stacks/worker/colab/runner.py bootstrap \
  --repo-dir /content/drive/MyDrive/discoverex/orchestrator \
  --cache-root /content/drive/MyDrive/discoverex/cache \
  --venv-dir /content/venv

/content/venv/bin/python infra/stacks/worker/colab/runner.py start \
  --skip-install \
  --checkpoint-dir /content/drive/MyDrive/orchestrator/checkpoints
```

The runtime layout is:

- repo: Google Drive
- pip/XDG cache: Google Drive
- virtualenv: `/content/venv`

The runner auto-loads repo-root `.env` when present and creates the checkpoint
directory after Drive is mounted. Do not create the virtualenv on Google Drive.

## 2. Operations

Other commands:

```bash
/content/venv/bin/python infra/stacks/worker/colab/runner.py status
/content/venv/bin/python infra/stacks/worker/colab/runner.py logs --tail 80
/content/venv/bin/python infra/stacks/worker/colab/runner.py stop
```

Optional notebook: `infra/stacks/worker/colab/worker_colab.ipynb`
It keeps only minimal bootstrap logic inline: the notebook can begin from a
session where only the notebook file is present, configure env, clone or
refresh the repo into Drive, and then invoke the checked-out
`infra/stacks/worker/colab/runner.py` with Colab-visible logs.

## 3. Artifact and Experiment Policy

- Record experiment metadata in MLflow (params/metrics/tags/status).
- Prefer `STORAGE_API_URL/artifact/...` for storage presigns.
- Upload and download artifact bytes through object-store presigned URLs, not through router proxying.
- Keep MinIO credentials out of workers.
- Persist uploaded `object_uri` references into MLflow tags (for example `artifact_manifest_uri`).
- In repo run mode, the runner now checks out the requested `ref` instead of detaching strictly by resolved SHA.

## 4. Auth Split

- External access credentials: `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`
- Internal backend secrets stay on the storage node gateway/backend services only
