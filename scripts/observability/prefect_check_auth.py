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
    parser = argparse.ArgumentParser(description="Check Prefect API auth and health.")
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    print_json({"ok": client.health(), "prefect_api_url": client.api_url})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
