from __future__ import annotations

import argparse

import pytest
from scripts.e2e.lib.shell_helpers.commands.prefect import (
    cmd_verify_prefect_priority,
    cmd_wait_prefect_state,
)


def test_wait_prefect_state_succeeds_when_target_state_observed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = iter(["PENDING", "RUNNING"])

    monkeypatch.setattr(
        "scripts.e2e.lib.shell_helpers.commands.prefect._read_flow_run_state",
        lambda *_args: next(states),
    )

    args = argparse.Namespace(
        prefect_api_url="http://prefect.example/api",
        flow_run_id="run-1",
        states="RUNNING,COMPLETED",
        fail_states="FAILED,CRASHED,CANCELLED",
        timeout_sec=5,
    )

    assert cmd_wait_prefect_state(args) == 0


def test_verify_prefect_priority_fails_when_lower_run_advances_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = iter(
        [
            "PENDING",
            "RUNNING",
        ]
    )

    monkeypatch.setattr(
        "scripts.e2e.lib.shell_helpers.commands.prefect._read_flow_run_state",
        lambda *_args: next(states),
    )

    args = argparse.Namespace(
        prefect_api_url="http://prefect.example/api",
        higher_flow_run_id="higher-run",
        lower_flow_run_id="lower-run",
        timeout_sec=5,
    )

    with pytest.raises(SystemExit, match="lower-priority flow run advanced"):
        cmd_verify_prefect_priority(args)


def test_verify_prefect_priority_passes_when_higher_run_starts_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = iter(
        [
            "RUNNING",
            "PENDING",
        ]
    )

    monkeypatch.setattr(
        "scripts.e2e.lib.shell_helpers.commands.prefect._read_flow_run_state",
        lambda *_args: next(states),
    )

    args = argparse.Namespace(
        prefect_api_url="http://prefect.example/api",
        higher_flow_run_id="higher-run",
        lower_flow_run_id="lower-run",
        timeout_sec=5,
    )

    assert cmd_verify_prefect_priority(args) == 0
