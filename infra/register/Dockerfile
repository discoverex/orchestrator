FROM python:3.11-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_PROJECT_ENVIRONMENT="/usr/local"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN useradd -m appuser

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=appuser:appuser src /app/src
COPY --chown=appuser:appuser infra/register/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

ENTRYPOINT ["/entrypoint.sh"]
