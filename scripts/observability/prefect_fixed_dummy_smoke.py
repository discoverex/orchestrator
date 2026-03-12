#!/usr/bin/env python3
from __future__ import annotations

import argparse

from scripts.observability.lib.prefect_observe_env import build_client
from scripts.observability.lib.prefect_observe_format import print_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test for fixed-dummy engine run."
    )
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    deployment = client.find_deployment("e2e-job/e2e-test")

    # Fixed dummy spec
    job_spec_raw = '{"run_mode": "inline", "engine": "fixed-dummy"}'
    out = client.create_flow_run(deployment["id"], job_spec_raw=job_spec_raw)
    print_json(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
