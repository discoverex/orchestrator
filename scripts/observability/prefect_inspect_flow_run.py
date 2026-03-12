#!/usr/bin/env python3
from __future__ import annotations

import argparse

from scripts.observability.lib.prefect_observe_env import build_client
from scripts.observability.lib.prefect_observe_format import print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch full Prefect flow run details.")
    parser.add_argument("--flow-run-id", required=True)
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    out = client.get_flow_run(args.flow_run_id)
    print_json(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
