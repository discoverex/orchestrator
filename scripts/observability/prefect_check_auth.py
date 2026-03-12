#!/usr/bin/env python3
from __future__ import annotations

import argparse

from scripts.observability.lib.prefect_observe_env import build_client
from scripts.observability.lib.prefect_observe_format import print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Prefect API auth and health.")
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    print_json({"ok": client.health(), "prefect_api_url": client.api_url})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
