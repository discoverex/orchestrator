FROM orchestrator-base:local
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libxcb1 libgl1\
 && rm -rf /var/lib/apt/lists/*

COPY --chown=appuser:appuser src/common /app/src/common
COPY --chown=appuser:appuser src/flows /app/src/flows
COPY --chown=appuser:appuser src/runner /app/src/runner
COPY --chown=appuser:appuser src/storage /app/src/storage
COPY --chown=appuser:appuser infra/images/entrypoints/worker-entrypoint.sh /worker-entrypoint.sh
RUN chmod +x /worker-entrypoint.sh

USER appuser

ENTRYPOINT ["/worker-entrypoint.sh"]
