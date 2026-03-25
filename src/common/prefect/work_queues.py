from __future__ import annotations

import argparse
from collections.abc import Sequence

from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import WorkPoolCreate
from prefect.exceptions import ObjectNotFound

DEFAULT_PRIMARY_QUEUE_PRIORITY = 1
DEFAULT_BATCH_QUEUE_PRIORITY = 10


def default_batch_queue_name(primary_queue: str) -> str:
    return f"{primary_queue}-batch"


def default_work_queue_names(
    primary_queue: str,
    *,
    batch_queue: str | None = None,
) -> list[str]:
    queue_names = [primary_queue, batch_queue or default_batch_queue_name(primary_queue)]
    deduped: list[str] = []
    for queue_name in queue_names:
        normalized = queue_name.strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def split_work_queue_names(raw: str | None) -> list[str]:
    if not raw:
        return []
    queue_names: list[str] = []
    for item in raw.split(","):
        normalized = item.strip()
        if normalized and normalized not in queue_names:
            queue_names.append(normalized)
    return queue_names


def work_queue_priorities(
    primary_queue: str,
    *,
    batch_queue: str | None = None,
) -> dict[str, int]:
    resolved_batch_queue = batch_queue or default_batch_queue_name(primary_queue)
    return {
        primary_queue: DEFAULT_PRIMARY_QUEUE_PRIORITY,
        resolved_batch_queue: DEFAULT_BATCH_QUEUE_PRIORITY,
    }


def ensure_work_pool_and_queues(
    work_pool: str,
    *,
    primary_queue: str,
    batch_queue: str | None = None,
) -> None:
    priorities = work_queue_priorities(primary_queue, batch_queue=batch_queue)
    with get_client(sync_client=True) as client:
        try:
            client.read_work_pool(work_pool)
        except ObjectNotFound:
            client.create_work_pool(WorkPoolCreate(name=work_pool, type="process"))

        for queue_name, priority in priorities.items():
            try:
                queue = client.read_work_queue_by_name(
                    queue_name,
                    work_pool_name=work_pool,
                )
            except ObjectNotFound:
                client.create_work_queue(
                    name=queue_name,
                    priority=priority,
                    work_pool_name=work_pool,
                )
                continue

            current_priority = getattr(queue, "priority", None)
            if current_priority != priority:
                client.update_work_queue(queue.id, priority=priority)


def build_worker_start_command(
    base_command: Sequence[str],
    *,
    work_queues: Sequence[str],
) -> list[str]:
    command = list(base_command)
    for queue_name in work_queues:
        command.extend(["--work-queue", queue_name])
    return command


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ensure a Prefect work pool and its primary/batch queues exist."
    )
    parser.add_argument("--pool", required=True)
    parser.add_argument("--primary-queue", required=True)
    parser.add_argument("--batch-queue", default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    ensure_work_pool_and_queues(
        args.pool,
        primary_queue=args.primary_queue,
        batch_queue=args.batch_queue,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
