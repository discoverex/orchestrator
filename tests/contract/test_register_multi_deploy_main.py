from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import pytest

import deployments.register.main as register


class _FakeSourceFlow:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def deploy(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


@contextmanager
def _patch_flow(fake: _FakeSourceFlow) -> Iterator[None]:
    register_any = cast(Any, register)
    original = register_any.flow.from_source
    register_any.flow.from_source = lambda **kwargs: fake
    try:
        yield
    finally:
        register_any.flow.from_source = original


def test_dual_mode_registers_fixed_and_colab(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSourceFlow()
    monkeypatch.setattr(
        register,
        "parse_args",
        lambda: argparse.Namespace(
            single_name=None,
            single_queue="default",
            pool="gpu-pool",
            fixed_name="e2e-test",
            fixed_queue="gpu-fixed",
            colab_name="e2e-test-colab",
            colab_queue="gpu-colab",
            compat_fixed_name="e2e-test-legacy",
            compat_fixed_queue="gpu-fixed",
            compat_colab_name="e2e-test-legacy-colab",
            compat_colab_queue="gpu-colab",
            register_compat_aliases=True,
            flow_source="/tmp/engine",
            flow_entrypoint="flows/run.py:engine_flow",
            version=None,
        ),
    )
    with _patch_flow(fake):
        register.main()
    assert len(fake.calls) == 4
    assert fake.calls[0]["name"] == "e2e-test"
    assert fake.calls[0]["work_pool_name"] == "gpu-pool"
    assert fake.calls[0]["work_queue_name"] == "gpu-fixed"
    assert fake.calls[1]["name"] == "e2e-test-colab"
    assert fake.calls[1]["work_queue_name"] == "gpu-colab"
    assert fake.calls[2]["name"] == "e2e-test-legacy"
    assert fake.calls[3]["name"] == "e2e-test-legacy-colab"


def test_single_mode_registers_compat_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeSourceFlow()
    monkeypatch.setattr(
        register,
        "parse_args",
        lambda: argparse.Namespace(
            single_name="e2e-test-legacy",
            single_queue="default",
            pool="gpu-pool",
            fixed_name="unused-fixed",
            fixed_queue="unused-fixed-queue",
            colab_name="unused-colab",
            colab_queue="unused-colab-queue",
            compat_fixed_name="compat-fixed",
            compat_fixed_queue="compat-fixed-queue",
            compat_colab_name="compat-colab",
            compat_colab_queue="compat-colab-queue",
            register_compat_aliases=True,
            flow_source=".",
            flow_entrypoint="src/flows/worker_runtime/flow.py:run_worker_job_flow",
            version="v1",
        ),
    )
    with _patch_flow(fake):
        register.main()
    assert len(fake.calls) == 1
    assert fake.calls[0]["name"] == "e2e-test-legacy"
    assert fake.calls[0]["work_queue_name"] == "default"
    assert fake.calls[0]["version"] == "v1"


def test_main_uses_explicit_source_and_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeSourceFlow()
    captured: dict[str, str] = {}
    register_any = cast(Any, register)
    original = register_any.flow.from_source
    monkeypatch.setattr(
        register,
        "parse_args",
        lambda: argparse.Namespace(
            single_name="e2e-test",
            single_queue="gpu-fixed",
            pool="gpu-pool",
            fixed_name="e2e-test",
            fixed_queue="gpu-fixed",
            colab_name="e2e-test-colab",
            colab_queue="gpu-colab",
            compat_fixed_name="e2e-test-legacy",
            compat_fixed_queue="gpu-fixed",
            compat_colab_name="e2e-test-legacy-colab",
            compat_colab_queue="gpu-colab",
            register_compat_aliases=True,
            flow_source="/srv/engine",
            flow_entrypoint="flows/runtime.py:engine_flow",
            version=None,
        ),
    )

    def _fake_from_source(*, source: str, entrypoint: str) -> _FakeSourceFlow:
        captured["source"] = source
        captured["entrypoint"] = entrypoint
        return fake

    register_any.flow.from_source = _fake_from_source
    try:
        register.main()
    finally:
        register_any.flow.from_source = original

    assert captured == {
        "source": "/srv/engine",
        "entrypoint": "flows/runtime.py:engine_flow",
    }
