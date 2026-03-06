FROM orchestrator-base:local

COPY --chown=appuser:appuser src/deployments /app/src/deployments
COPY --chown=appuser:appuser src/flows /app/src/flows
COPY --chown=appuser:appuser src/runner /app/src/runner
COPY --chown=appuser:appuser infra/images/entrypoints/register-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser
ENTRYPOINT ["/entrypoint.sh"]
