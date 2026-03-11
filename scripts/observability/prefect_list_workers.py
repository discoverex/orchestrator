#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.observability.lib.prefect_observe import build_client, print_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="List Prefect workers in a work pool.")
    parser.add_argument("--work-pool", default="gpu-pool")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    print_json(client.list_workers(args.work_pool, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
