from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import deployments.register as register


class _FakeSourceFlow:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def deploy(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


@contextmanager
def _patch_flow(fake: _FakeSourceFlow) -> Iterator[None]:
    original = register.flow.from_source
    register.flow.from_source = lambda **kwargs: fake  # type: ignore[assignment]
    try:
        yield
    finally:
        register.flow.from_source = original  # type: ignore[assignment]


def test_dual_mode_registers_fixed_and_colab(monkeypatch) -> None:  # noqa: ANN001
    fake = _FakeSourceFlow()
    monkeypatch.setattr(
        register,
        "parse_args",
        lambda: register.argparse.Namespace(
            single_name=None,
            single_queue="default",
            pool="gpu-pool",
            fixed_name="engine-run",
            fixed_queue="gpu-fixed",
            colab_name="engine-run-colab",
            colab_queue="gpu-colab",
            version=None,
        ),
    )
    with _patch_flow(fake):
        register.main()
    assert len(fake.calls) == 2
    assert fake.calls[0]["name"] == "engine-run"
    assert fake.calls[0]["work_pool_name"] == "gpu-pool"
    assert fake.calls[0]["work_queue_name"] == "gpu-fixed"
    assert fake.calls[1]["name"] == "engine-run-colab"
    assert fake.calls[1]["work_queue_name"] == "gpu-colab"


def test_single_mode_registers_compat_deployment(monkeypatch) -> None:  # noqa: ANN001
    fake = _FakeSourceFlow()
    monkeypatch.setattr(
        register,
        "parse_args",
        lambda: register.argparse.Namespace(
            single_name="engine-run",
            single_queue="default",
            pool="gpu-pool",
            fixed_name="unused-fixed",
            fixed_queue="unused-fixed-queue",
            colab_name="unused-colab",
            colab_queue="unused-colab-queue",
            version="v1",
        ),
    )
    with _patch_flow(fake):
        register.main()
    assert len(fake.calls) == 1
    assert fake.calls[0]["name"] == "engine-run"
    assert fake.calls[0]["work_queue_name"] == "default"
    assert fake.calls[0]["version"] == "v1"
