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
    print_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure a Prefect work pool exists.")
    parser.add_argument("--work-pool", required=True)
    parser.add_argument("--type", default="process")
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    row = client.ensure_work_pool(args.work_pool, pool_type=args.type)
    print_json(
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "type": row.get("type"),
            "is_paused": row.get("is_paused"),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
