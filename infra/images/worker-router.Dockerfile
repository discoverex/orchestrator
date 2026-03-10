FROM orchestrator-base:local

COPY --chown=appuser:appuser src/common /app/src/common
COPY --chown=appuser:appuser src/worker_router /app/src/worker_router

USER appuser

EXPOSE 8200
HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
  CMD curl -fsS http://localhost:8200/healthz >/dev/null || exit 1

CMD ["uvicorn", "worker_router.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8200"]
