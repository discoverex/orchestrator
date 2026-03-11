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
    summarize_deployment,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a Prefect deployment.")
    parser.add_argument("--deployment-name", required=True)
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    row = client.find_deployment(args.deployment_name)
    print_json(summarize_deployment(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
