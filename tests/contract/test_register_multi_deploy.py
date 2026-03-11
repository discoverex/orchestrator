from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import pytest

import deployments.register as register


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


def test_single_mode_registers_compat_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeSourceFlow()
    monkeypatch.setattr(
        register,
        "parse_args",
        lambda: argparse.Namespace(
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


def test_parse_args_uses_expected_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["register.py"])

    args = register.parse_args()

    assert args.single_name is None
    assert args.single_queue == "default"
    assert args.pool == "gpu-pool"
    assert args.fixed_name == "engine-run"
    assert args.fixed_queue == "gpu-fixed"
    assert args.colab_name == "engine-run-colab"
    assert args.colab_queue == "gpu-colab"
    assert args.version is None


def test_parse_args_accepts_explicit_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "register.py",
            "--single-name",
            "one",
            "--single-queue",
            "queue-a",
            "--pool",
            "pool-a",
            "--fixed-name",
            "fixed-a",
            "--fixed-queue",
            "fixed-q",
            "--colab-name",
            "colab-a",
            "--colab-queue",
            "colab-q",
            "--version",
            "v2",
        ],
    )

    args = register.parse_args()

    assert args.single_name == "one"
    assert args.single_queue == "queue-a"
    assert args.pool == "pool-a"
    assert args.fixed_name == "fixed-a"
    assert args.fixed_queue == "fixed-q"
    assert args.colab_name == "colab-a"
    assert args.colab_queue == "colab-q"
    assert args.version == "v2"
