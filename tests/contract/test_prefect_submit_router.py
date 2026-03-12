from __future__ import annotations

import sys

import pytest

from .prefect_submit_router_helpers import (
    capture_json_stdout,
    fake_args,
    load_router_module,
)


def test_router_diverts_when_fixed_running(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = load_router_module()
    monkeypatch.setattr(
        mod, "_build_parser", lambda: fake_args(divert_when_running="true")
    )
    monkeypatch.setattr(mod, "scheduled_count_for_queue", lambda q: 0)
    monkeypatch.setattr(
        mod, "running_count_for_queue", lambda q: 1 if q == "gpu-fixed" else 0
    )
    monkeypatch.setattr(mod, "find_deployment_id", lambda d: f"id-{d}")
    monkeypatch.setattr(
        mod,
        "create_flow_run",
        lambda dep_id, params, flow_run_name=None: {
            "id": "run-1",
            "name": flow_run_name or "r1",
        },
    )

    out = capture_json_stdout(mod.main)
    assert out["selected_deployment"] == "e2e-test-colab"
    assert out["reason"] == "running-diverted-to-secondary"


def test_router_strict_priority_keeps_preferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = load_router_module()
    monkeypatch.setattr(mod, "_build_parser", lambda: fake_args(strict_priority="true"))
    monkeypatch.setattr(mod, "scheduled_count_for_queue", lambda q: 100)
    monkeypatch.setattr(mod, "running_count_for_queue", lambda q: 100)
    monkeypatch.setattr(mod, "find_deployment_id", lambda d: f"id-{d}")
    monkeypatch.setattr(
        mod,
        "create_flow_run",
        lambda dep_id, params, flow_run_name=None: {
            "id": "run-2",
            "name": flow_run_name or "r2",
        },
    )

    out = capture_json_stdout(mod.main)
    assert out["selected_deployment"] == "e2e-test"
    assert out["reason"] == "strict-priority-selected-preferred"


def test_router_forwards_job_name_to_flow_run_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = load_router_module()
    job_spec = (
        '{"run_mode":"inline","engine":"shell","job_name":"my-job","entrypoint":["ls"]}'
    )
    monkeypatch.setattr(mod, "_build_parser", lambda: fake_args(job_spec_json=job_spec))
    monkeypatch.setattr(mod, "scheduled_count_for_queue", lambda q: 0)
    monkeypatch.setattr(mod, "running_count_for_queue", lambda q: 0)
    monkeypatch.setattr(mod, "find_deployment_id", lambda d: f"id-{d}")
    monkeypatch.setattr(
        mod,
        "create_flow_run",
        lambda dep_id, params, flow_run_name=None: {
            "id": "run-3",
            "name": flow_run_name or "generated",
        },
    )

    out = capture_json_stdout(mod.main)
    assert out["flow_run_id"] == "run-3"


def test_router_uses_new_default_deployment_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = load_router_module()
    monkeypatch.delenv("ROUTER_FIXED_DEPLOYMENT", raising=False)
    monkeypatch.delenv("ROUTER_COLAB_DEPLOYMENT", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prefect_submit_router.py",
            "--job-spec-json",
            '{"run_mode":"inline","engine":"shell","entrypoint":["ls"]}',
        ],
    )
    monkeypatch.setattr(mod, "scheduled_count_for_queue", lambda q: 0)
    monkeypatch.setattr(mod, "running_count_for_queue", lambda q: 0)
    monkeypatch.setattr(mod, "find_deployment_id", lambda d: f"id-{d}")
    monkeypatch.setattr(
        mod,
        "create_flow_run",
        lambda dep_id, params, flow_run_name=None: {
            "id": "run-defaults",
            "name": "gen",
        },
    )

    out = capture_json_stdout(mod.main)
    assert out["selected_deployment"] == "e2e-test"
