from __future__ import annotations

import sys

import pytest

import deployments.register.main as register


def test_parse_args_uses_expected_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["register.py"])

    args = register.parse_args()

    assert args.single_name is None
    assert args.single_queue == "default"
    assert args.spec_file == register.DEFAULT_SPEC_FILE
    assert args.pool == "gpu-pool"
    assert args.fixed_name is None
    assert args.fixed_queue is None
    assert args.colab_name is None
    assert args.colab_queue is None
    assert args.compat_fixed_name is None
    assert args.compat_fixed_queue is None
    assert args.compat_colab_name is None
    assert args.compat_colab_queue is None
    assert args.register_compat_aliases is True
    assert args.flow_source == register.DEFAULT_FLOW_SOURCE
    assert args.flow_entrypoint is None
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
            "--spec-file",
            "deployments/custom.yaml",
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
            "--compat-fixed-name",
            "compat-fixed",
            "--compat-fixed-queue",
            "compat-fixed-q",
            "--compat-colab-name",
            "compat-colab",
            "--compat-colab-queue",
            "compat-colab-q",
            "--no-register-compat-aliases",
            "--flow-source",
            "/srv/engine",
            "--flow-entrypoint",
            "engine/flows.py:run",
            "--version",
            "v2",
        ],
    )

    args = register.parse_args()

    assert args.single_name == "one"
    assert args.single_queue == "queue-a"
    assert args.spec_file == "deployments/custom.yaml"
    assert args.pool == "pool-a"
    assert args.fixed_name == "fixed-a"
    assert args.fixed_queue == "fixed-q"
    assert args.colab_name == "colab-a"
    assert args.colab_queue == "colab-q"
    assert args.compat_fixed_name == "compat-fixed"
    assert args.compat_fixed_queue == "compat-fixed-q"
    assert args.compat_colab_name == "compat-colab"
    assert args.compat_colab_queue == "compat-colab-q"
    assert args.register_compat_aliases is False
    assert args.flow_source == "/srv/engine"
    assert args.flow_entrypoint == "engine/flows.py:run"
    assert args.version == "v2"
