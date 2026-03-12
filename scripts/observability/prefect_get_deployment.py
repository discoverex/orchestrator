#!/usr/bin/env python3
from __future__ import annotations

import argparse

from scripts.observability.lib.prefect_observe_env import build_client
from scripts.observability.lib.prefect_observe_format import (
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
