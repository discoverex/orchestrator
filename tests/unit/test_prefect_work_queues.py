from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import common.prefect.work_queues as work_queues


def test_default_work_queue_names_adds_batch_queue() -> None:
    assert work_queues.default_work_queue_names("gpu-fixed") == [
        "gpu-fixed",
        "gpu-fixed-batch",
    ]


def test_split_work_queue_names_dedupes_and_trims() -> None:
    assert work_queues.split_work_queue_names(" gpu-fixed, gpu-fixed-batch ,gpu-fixed ") == [
        "gpu-fixed",
        "gpu-fixed-batch",
    ]


def test_build_worker_start_command_repeats_work_queue_flags() -> None:
    command = work_queues.build_worker_start_command(
        ["prefect", "worker", "start"],
        work_queues=["gpu-fixed", "gpu-fixed-batch"],
    )

    assert command == [
        "prefect",
        "worker",
        "start",
        "--work-queue",
        "gpu-fixed",
        "--work-queue",
        "gpu-fixed-batch",
    ]


class _FakeClient:
    def __init__(self) -> None:
        self.pool_exists = False
        self.queues: dict[str, Any] = {}
        self.created_pools: list[tuple[str, str]] = []
        self.created_queues: list[tuple[str, int, str | None]] = []
        self.updated_queues: list[tuple[str, int]] = []

    def read_work_pool(self, name: str) -> object:
        if not self.pool_exists:
            raise work_queues.ObjectNotFound("pool")
        return object()

    def create_work_pool(self, work_pool: Any) -> object:
        self.pool_exists = True
        self.created_pools.append((work_pool.name, work_pool.type))
        return object()

    def read_work_queue_by_name(self, name: str, work_pool_name: str | None = None) -> Any:
        if name not in self.queues:
            raise work_queues.ObjectNotFound("queue")
        return self.queues[name]

    def create_work_queue(
        self,
        *,
        name: str,
        priority: int | None = None,
        work_pool_name: str | None = None,
        **_: Any,
    ) -> Any:
        queue = SimpleNamespace(id=f"{name}-id", priority=priority)
        self.queues[name] = queue
        self.created_queues.append((name, int(priority or 0), work_pool_name))
        return queue

    def update_work_queue(self, queue_id: str, **kwargs: Any) -> None:
        priority = int(kwargs["priority"])
        self.updated_queues.append((queue_id, priority))


@contextmanager
def _patched_client(fake: _FakeClient):
    original = work_queues.get_client

    @contextmanager
    def _manager(*_: Any, **__: Any):
        yield fake

    work_queues.get_client = _manager  # type: ignore[assignment]
    try:
        yield
    finally:
        work_queues.get_client = original  # type: ignore[assignment]


def test_ensure_work_pool_and_queues_creates_pool_and_expected_queues() -> None:
    fake = _FakeClient()

    with _patched_client(fake):
        work_queues.ensure_work_pool_and_queues(
            "gpu-pool",
            primary_queue="gpu-fixed",
        )

    assert fake.created_pools == [("gpu-pool", "process")]
    assert fake.created_queues == [
        ("gpu-fixed", 1, "gpu-pool"),
        ("gpu-fixed-batch", 10, "gpu-pool"),
    ]


def test_ensure_work_pool_and_queues_updates_priority_when_needed() -> None:
    fake = _FakeClient()
    fake.pool_exists = True
    fake.queues = {
        "gpu-fixed": SimpleNamespace(id="fixed-id", priority=5),
        "gpu-fixed-batch": SimpleNamespace(id="batch-id", priority=10),
    }

    with _patched_client(fake):
        work_queues.ensure_work_pool_and_queues(
            "gpu-pool",
            primary_queue="gpu-fixed",
        )

    assert fake.updated_queues == [("fixed-id", 1)]
