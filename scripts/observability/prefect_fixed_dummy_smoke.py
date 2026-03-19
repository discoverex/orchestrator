#!/usr/bin/env python3
from __future__ import annotations

import argparse

from common.prefect.deployment_targets import default_fixed_deployment_fqn
from scripts.observability.lib.prefect_observe_env import build_client
from scripts.observability.lib.prefect_observe_format import print_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test for fixed-dummy engine run."
    )
    parser.add_argument("--env-file", default=None)
    parser.add_argument(
        "--deployment-name",
        default=default_fixed_deployment_fqn(),
        help="Target deployment name (flow/deployment)",
    )
    args = parser.parse_args()

    client = build_client(args.env_file)
    deployment = client.find_deployment(args.deployment_name)

    out = client.create_flow_run(
        deployment["id"],
        parameters={
            "run_mode": "inline",
            "engine": "fixed-dummy",
            "entrypoint": ["/bin/sh", "-lc", "echo dummy"],
            "inputs": {},
            "env": {},
            "outputs_prefix": None,
        },
    )
    print_json(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
