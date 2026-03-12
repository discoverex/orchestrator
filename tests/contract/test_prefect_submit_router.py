from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest


def _load_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "ops"
        / "prefect_submit_router.py"
    )
    spec = importlib.util.spec_from_file_location("prefect_submit_router", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_router_diverts_when_fixed_running(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    monkeypatch.setattr(
        mod,
        "_build_parser",
        lambda: _FakeParser(
            {
                "mode": "fixed-first",
                "strict_priority": "false",
                "queue_depth_threshold": 1,
                "divert_when_running": "true",
                "fixed_deployment": "discoverex-engine-run",
                "colab_deployment": "discoverex-engine-run-colab",
                "fixed_queue": "gpu-fixed",
                "colab_queue": "gpu-colab",
                "job_spec_json": '{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo test"],"config":null,"inputs":{},"env":{},"outputs_prefix":null}',
                "job_spec_file": None,
                "resume_key": None,
                "checkpoint_dir": None,
                "parameters_json": None,
            }
        ),
    )
    monkeypatch.setattr(mod, "_scheduled_count_for_queue", lambda q: 0)
    monkeypatch.setattr(
        mod, "_running_count_for_queue", lambda q: 1 if q == "gpu-fixed" else 0
    )
    monkeypatch.setattr(mod, "_find_deployment_id", lambda d: f"id-{d}")
    monkeypatch.setattr(
        mod,
        "_create_flow_run",
        lambda dep_id, params, flow_run_name=None: {
            "id": "run-1",
            "name": flow_run_name or "r1",
        },
    )

    out = _capture_json_stdout(mod.main)
    assert out["selected_deployment"] == "discoverex-engine-run-colab"
    assert out["reason"] == "running-diverted-to-secondary"


def test_router_strict_priority_keeps_preferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()
    monkeypatch.setattr(
        mod,
        "_build_parser",
        lambda: _FakeParser(
            {
                "mode": "fixed-first",
                "strict_priority": "true",
                "queue_depth_threshold": 0,
                "divert_when_running": "true",
                "fixed_deployment": "discoverex-engine-run",
                "colab_deployment": "discoverex-engine-run-colab",
                "fixed_queue": "gpu-fixed",
                "colab_queue": "gpu-colab",
                "job_spec_json": '{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo test"],"config":null,"inputs":{},"env":{},"outputs_prefix":null}',
                "job_spec_file": None,
                "resume_key": None,
                "checkpoint_dir": None,
                "parameters_json": None,
            }
        ),
    )
    monkeypatch.setattr(
        mod, "_scheduled_count_for_queue", lambda q: 100 if q == "gpu-fixed" else 0
    )
    monkeypatch.setattr(
        mod, "_running_count_for_queue", lambda q: 100 if q == "gpu-fixed" else 0
    )
    monkeypatch.setattr(mod, "_find_deployment_id", lambda d: f"id-{d}")
    monkeypatch.setattr(
        mod,
        "_create_flow_run",
        lambda dep_id, params, flow_run_name=None: {
            "id": "run-2",
            "name": flow_run_name or "r2",
        },
    )

    out = _capture_json_stdout(mod.main)
    assert out["selected_deployment"] == "discoverex-engine-run"
    assert out["reason"] == "strict-priority-selected-preferred"


def test_router_forwards_job_name_to_flow_run_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()
    monkeypatch.setattr(
        mod,
        "_build_parser",
        lambda: _FakeParser(
            {
                "mode": "fixed-first",
                "strict_priority": "true",
                "queue_depth_threshold": 0,
                "divert_when_running": "true",
                "fixed_deployment": "discoverex-engine-run",
                "colab_deployment": "discoverex-engine-run-colab",
                "fixed_queue": "gpu-fixed",
                "colab_queue": "gpu-colab",
                "job_spec_json": '{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo test"],"config":null,"job_name":"my-job","inputs":{},"env":{},"outputs_prefix":null}',
                "job_spec_file": None,
                "resume_key": None,
                "checkpoint_dir": None,
                "parameters_json": None,
            }
        ),
    )
    monkeypatch.setattr(mod, "_scheduled_count_for_queue", lambda q: 0)
    monkeypatch.setattr(mod, "_running_count_for_queue", lambda q: 0)
    monkeypatch.setattr(mod, "_find_deployment_id", lambda d: f"id-{d}")

    calls: dict[str, str | None] = {}

    def _fake_create(
        dep_id: str, params: dict[str, object], flow_run_name: str | None = None
    ) -> dict[str, str]:
        _ = (dep_id, params)
        calls["name"] = flow_run_name
        return {"id": "run-3", "name": flow_run_name or "generated"}

    monkeypatch.setattr(mod, "_create_flow_run", _fake_create)
    out = _capture_json_stdout(mod.main)
    assert calls["name"] == "my-job"
    assert out["flow_run_name"] == "my-job"


def test_router_uses_new_default_deployment_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()
    monkeypatch.delenv("ROUTER_FIXED_DEPLOYMENT", raising=False)
    monkeypatch.delenv("ROUTER_COLAB_DEPLOYMENT", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prefect_submit_router.py",
            "--job-spec-json",
            '{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo test"],"config":null,"inputs":{},"env":{},"outputs_prefix":null}',
        ],
    )
    monkeypatch.setattr(mod, "_scheduled_count_for_queue", lambda q: 0)
    monkeypatch.setattr(mod, "_running_count_for_queue", lambda q: 0)
    monkeypatch.setattr(mod, "_find_deployment_id", lambda d: f"id-{d}")
    monkeypatch.setattr(
        mod,
        "_create_flow_run",
        lambda dep_id, params, flow_run_name=None: {
            "id": "run-defaults",
            "name": flow_run_name or "generated",
        },
    )

    out = _capture_json_stdout(mod.main)
    assert out["selected_deployment"] == "discoverex-engine-run"


class _FakeParser:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def parse_args(self) -> object:
        return type("Args", (), self._payload)()


def _capture_json_stdout(fn: Callable[[], int]) -> dict[str, Any]:
    import io
    import json
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn()
    assert rc == 0
    return cast(dict[str, Any], json.loads(buf.getvalue().strip()))
