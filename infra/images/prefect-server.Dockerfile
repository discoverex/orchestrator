FROM prefecthq/prefect:3-latest

ENV PYTHONUNBUFFERED=1
WORKDIR /opt/orchestrator

COPY scripts/ops/prefect_flush_completed.py /opt/orchestrator/scripts/ops/prefect_flush_completed.py
COPY scripts/ops/prefect_prune_completed.py /opt/orchestrator/scripts/ops/prefect_prune_completed.py
COPY scripts/ops/prefect_maintenance_loop.sh /opt/orchestrator/scripts/ops/prefect_maintenance_loop.sh

RUN chmod +x /opt/orchestrator/scripts/ops/prefect_maintenance_loop.sh
