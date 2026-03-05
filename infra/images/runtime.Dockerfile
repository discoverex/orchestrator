FROM python:3.11-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /bin/uv

ENV UV_PROJECT_ENVIRONMENT="/opt/venv"
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


FROM python:3.11-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH=/opt/venv/bin:$PATH \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 10001 appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv


FROM base AS storage-gateway

COPY --chown=appuser:appuser src/storage /app/src/storage
COPY --chown=appuser:appuser src/storage_gateway /app/src/storage_gateway
COPY --chown=appuser:appuser src/storage_explorer /app/src/storage_explorer

USER appuser

EXPOSE 8100
HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
  CMD curl -fsS http://localhost:8100/healthz >/dev/null || exit 1

CMD ["uvicorn", "storage_gateway.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8100"]


FROM base AS worker

COPY --chown=appuser:appuser src/flows /app/src/flows
COPY --chown=appuser:appuser src/runner /app/src/runner
COPY --chown=appuser:appuser src/storage /app/src/storage
COPY --chown=appuser:appuser infra/images/worker-entrypoint.sh /worker-entrypoint.sh
RUN chmod +x /worker-entrypoint.sh

USER appuser

ENTRYPOINT ["/worker-entrypoint.sh"]


FROM base AS register

COPY --chown=appuser:appuser src/deployments /app/src/deployments
COPY --chown=appuser:appuser src/flows /app/src/flows
COPY --chown=appuser:appuser infra/register/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser
ENTRYPOINT ["/entrypoint.sh"]
