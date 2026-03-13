from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

COLAB_DIR = (
    Path(__file__).resolve().parents[2] / "infra" / "stacks" / "worker" / "colab"
)


def _load_module(name: str) -> ModuleType:
    if str(COLAB_DIR) not in sys.path:
        sys.path.insert(0, str(COLAB_DIR))
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def _build_config(runtime_mod: ModuleType, tmp_path: Path) -> Any:
    return runtime_mod.ColabRuntimeConfig(
        repo_dir=tmp_path / "repo",
        cache_root=tmp_path / "cache",
        checkpoint_dir=tmp_path / "checkpoints",
        pid_file=tmp_path / "worker.pid",
        log_file=tmp_path / "worker.log",
        python_bin="python3",
    )


def test_prefect_env_sets_default_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _load_module("worker.runtime")
    monkeypatch.delenv("PREFECT_WORK_QUEUE", raising=False)
    monkeypatch.delenv("PREFECT_CLIENT_CUSTOM_HEADERS", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)

    env = runtime.prefect_env()

    assert env["PREFECT_WORK_QUEUE"] == "gpu-colab"
    assert "PREFECT_CLIENT_CUSTOM_HEADERS" not in env


def test_populate_colab_env_maps_cf_access_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _load_module("worker.runtime")
    config = _build_config(runtime, tmp_path)
    monkeypatch.delenv("PREFECT_CLIENT_CUSTOM_HEADERS", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "prefect-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "prefect-secret")

    snapshot = runtime.populate_colab_env(config)

    assert snapshot["prefect_work_queue"] == "gpu-colab"
    assert runtime.clean_env_value(os.environ["CF_ACCESS_CLIENT_ID"]) == "prefect-id"
    assert "CF-Access-Client-Id" in os.environ["PREFECT_CLIENT_CUSTOM_HEADERS"]


def test_load_dotenv_sets_missing_values_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _load_module("worker.runtime")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PREFECT_API_URL=https://prefect.example/api\nPREFECT_WORK_POOL=gpu-pool\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("PREFECT_API_URL", raising=False)
    monkeypatch.setenv("PREFECT_WORK_POOL", "existing-pool")

    runtime.load_dotenv(env_path)

    assert os.environ["PREFECT_API_URL"] == "https://prefect.example/api"
    assert os.environ["PREFECT_WORK_POOL"] == "existing-pool"


def test_resolve_path_uses_repo_root_for_relative_paths() -> None:
    runtime = _load_module("worker.runtime")

    resolved = runtime.resolve_path(Path("infra/stacks/worker/colab"))

    assert resolved == runtime.REPO_ROOT / "infra/stacks/worker/colab"
