from __future__ import annotations

import argparse
import time
from typing import Any, cast
from urllib import error, request

from ..http import http_json


def cmd_poll_prefect_completion(args: argparse.Namespace) -> int:
    api_url = args.prefect_api_url.rstrip("/")
    terminal_success = {"COMPLETED"}
    terminal_fail = {"FAILED", "CRASHED", "CANCELLED"}
    transient_statuses = {403, 404, 429, 500, 502, 503, 504}

    deadline = time.time() + args.timeout_sec
    while time.time() < deadline:
        try:
            payload = cast(
                dict[str, Any],
                http_json("GET", f"{api_url}/flow_runs/{args.flow_run_id}", timeout=10),
            )
        except error.HTTPError as exc:
            if exc.code in transient_statuses:
                time.sleep(2)
                continue
            raise
        state_type_raw = payload.get("state_type")
        if not state_type_raw:
            state = payload.get("state")
            if isinstance(state, dict):
                state_type_raw = state.get("type")
        state_type = str(state_type_raw or "").upper()
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
