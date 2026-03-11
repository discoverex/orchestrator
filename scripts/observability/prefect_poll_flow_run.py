#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.observability.lib.prefect_observe import (  # noqa: E402
    build_client,
    poll_flow_run,
    print_json,
    summarize_flow_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll a Prefect flow run.")
    parser.add_argument("--flow-run-id", required=True)
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--poll-interval-sec", type=int, default=5)
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    row = poll_flow_run(
        client,
        args.flow_run_id,
        timeout_sec=args.timeout_sec,
        poll_interval_sec=args.poll_interval_sec,
    )
    print_json(summarize_flow_run(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
