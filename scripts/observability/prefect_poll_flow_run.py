#!/usr/bin/env python3
from __future__ import annotations

import argparse

from scripts.observability.lib.prefect_observe_env import build_client
from scripts.observability.lib.prefect_observe_format import (
    poll_flow_run,
    print_json,
    summarize_flow_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll a Prefect flow run.")
    parser.add_argument("--flow-run-id", required=True)
    parser.add_argument("--timeout-sec", type=int, default=300)
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    row = poll_flow_run(client, args.flow_run_id, timeout_sec=args.timeout_sec)
    print_json(summarize_flow_run(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
