from __future__ import annotations

import argparse
import time
from typing import Any, cast
from urllib import error, request

from ..http import http_json


def _read_flow_run_state(api_url: str, flow_run_id: str) -> str:
    payload = cast(
        dict[str, Any],
        http_json("GET", f"{api_url}/flow_runs/{flow_run_id}", timeout=10),
    )
    state_type_raw = payload.get("state_type")
    if not state_type_raw:
        state = payload.get("state")
        if isinstance(state, dict):
            state_type_raw = state.get("type")
    return str(state_type_raw or "").upper()


def cmd_poll_prefect_completion(args: argparse.Namespace) -> int:
    api_url = args.prefect_api_url.rstrip("/")
    terminal_success = {"COMPLETED"}
    terminal_fail = {"FAILED", "CRASHED", "CANCELLED"}
    transient_statuses = {403, 404, 429, 500, 502, 503, 504}

    deadline = time.time() + args.timeout_sec
    while time.time() < deadline:
        try:
            state_type = _read_flow_run_state(api_url, args.flow_run_id)
        except error.HTTPError as exc:
            if exc.code in transient_statuses:
                time.sleep(2)
                continue
            raise
        if state_type in terminal_success:
            print("COMPLETED")
            return 0
        if state_type in terminal_fail:
            print(state_type)
            return 2
        time.sleep(2)

    print("TIMEOUT")
    return 3


def cmd_verify_prune_removed(args: argparse.Namespace) -> int:
    api_url = args.prefect_api_url.rstrip("/")
    req = request.Request(f"{api_url}/flow_runs/{args.flow_run_id}", method="GET")
    try:
        with request.urlopen(req, timeout=10):
            raise SystemExit("flow run still exists after prune")
    except error.HTTPError as exc:
        if exc.code != 404:
            raise
    print("prune-ok")
    return 0


def cmd_wait_prefect_state(args: argparse.Namespace) -> int:
    api_url = args.prefect_api_url.rstrip("/")
    target_states = {
        state.strip().upper() for state in str(args.states).split(",") if state.strip()
    }
    fail_states = {
        state.strip().upper()
        for state in str(args.fail_states).split(",")
        if state.strip()
    }
    deadline = time.time() + args.timeout_sec
    while time.time() < deadline:
        state_type = _read_flow_run_state(api_url, args.flow_run_id)
        if state_type in target_states:
            print(state_type)
            return 0
        if state_type in fail_states:
            print(state_type)
            return 2
        time.sleep(2)

    print("TIMEOUT")
    return 3


def cmd_verify_prefect_priority(args: argparse.Namespace) -> int:
    api_url = args.prefect_api_url.rstrip("/")
    higher_running_states = {"RUNNING", "COMPLETED"}
    lower_disallowed_states = {"RUNNING", "COMPLETED"}
    fail_states = {"FAILED", "CRASHED", "CANCELLED"}
    deadline = time.time() + args.timeout_sec

    while time.time() < deadline:
        higher_state = _read_flow_run_state(api_url, args.higher_flow_run_id)
        lower_state = _read_flow_run_state(api_url, args.lower_flow_run_id)

        if higher_state in fail_states:
            raise SystemExit(f"higher-priority flow run failed early: {higher_state}")
        if lower_state in fail_states:
            raise SystemExit(f"lower-priority flow run failed early: {lower_state}")
        if (
            lower_state in lower_disallowed_states
            and higher_state not in higher_running_states
        ):
            raise SystemExit(
                "lower-priority flow run advanced before higher-priority flow run"
            )
        if (
            higher_state in higher_running_states
            and lower_state not in lower_disallowed_states
        ):
            print("priority-ok")
            return 0
        time.sleep(2)

    print("TIMEOUT")
    return 3
