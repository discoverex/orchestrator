FROM orchestrator-base:local

COPY --chown=appuser:appuser src/flows /app/src/flows
COPY --chown=appuser:appuser src/runner /app/src/runner
COPY --chown=appuser:appuser src/storage /app/src/storage
COPY --chown=appuser:appuser infra/images/entrypoints/worker-entrypoint.sh /worker-entrypoint.sh
RUN chmod +x /worker-entrypoint.sh

USER appuser

ENTRYPOINT ["/worker-entrypoint.sh"]
