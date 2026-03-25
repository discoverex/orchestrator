#!/usr/bin/env python3
from __future__ import annotations

import argparse

from scripts.observability.lib.prefect_observe_env import build_client
from scripts.observability.lib.prefect_observe_format import print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="List Prefect workers in a work pool.")
    parser.add_argument("--work-pool", default="gpu-pool")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    rows = client.list_workers(args.work_pool, limit=args.limit)
    print_json(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
