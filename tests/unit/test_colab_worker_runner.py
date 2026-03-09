from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "infra"
        / "stacks"
        / "worker"
        / "colab"
        / "colab_worker_runner.py"
    )
    spec = importlib.util.spec_from_file_location("colab_worker_runner", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_prefect_env_sets_default_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    monkeypatch.delenv("PREFECT_WORK_QUEUE", raising=False)
    monkeypatch.delenv("PREFECT_CLIENT_CUSTOM_HEADERS", raising=False)
    monkeypatch.delenv("PREFECT_CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("PREFECT_CF_ACCESS_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)

    env = mod._prefect_env()

    assert env["PREFECT_WORK_QUEUE"] == "gpu-colab"
    assert "PREFECT_CLIENT_CUSTOM_HEADERS" not in env


def test_prefect_env_maps_prefect_cf_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()
    monkeypatch.delenv("PREFECT_CLIENT_CUSTOM_HEADERS", raising=False)
    monkeypatch.setenv("PREFECT_CF_ACCESS_CLIENT_ID", "prefect-id")
    monkeypatch.setenv("PREFECT_CF_ACCESS_CLIENT_SECRET", "prefect-secret")
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)

    env = mod._prefect_env()

    assert json.loads(env["PREFECT_CLIENT_CUSTOM_HEADERS"]) == {
        "CF-Access-Client-Id": "prefect-id",
        "CF-Access-Client-Secret": "prefect-secret",
    }


def test_prefect_env_maps_generic_cf_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()
    monkeypatch.delenv("PREFECT_CLIENT_CUSTOM_HEADERS", raising=False)
    monkeypatch.delenv("PREFECT_CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("PREFECT_CF_ACCESS_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "generic-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "generic-secret")

    env = mod._prefect_env()

    assert json.loads(env["PREFECT_CLIENT_CUSTOM_HEADERS"]) == {
        "CF-Access-Client-Id": "generic-id",
        "CF-Access-Client-Secret": "generic-secret",
    }


def test_prefect_env_keeps_existing_custom_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()
    monkeypatch.setenv("PREFECT_CLIENT_CUSTOM_HEADERS", '{"X-Test":"1"}')
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "generic-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "generic-secret")

    env = mod._prefect_env()

    assert env["PREFECT_CLIENT_CUSTOM_HEADERS"] == '{"X-Test":"1"}'
