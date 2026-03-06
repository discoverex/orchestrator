FROM orchestrator-base:local

COPY --chown=appuser:appuser src/common /app/src/common
COPY --chown=appuser:appuser src/storage /app/src/storage
COPY --chown=appuser:appuser src/storage_gateway /app/src/storage_gateway

USER appuser

EXPOSE 8100
HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
  CMD curl -fsS http://localhost:8100/healthz >/dev/null || exit 1

CMD ["uvicorn", "storage_gateway.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8100"]
