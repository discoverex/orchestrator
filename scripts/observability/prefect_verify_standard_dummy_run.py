#!/usr/bin/env python3
from __future__ import annotations

import argparse

from common.prefect.deployment_targets import default_fixed_deployment_fqn
from scripts.observability.lib.prefect_observe_env import build_client
from scripts.observability.lib.prefect_observe_format import (
    poll_flow_run,
    print_json,
    summarize_flow_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit and verify a standard dummy run."
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
            "run_mode": "repo",
            "engine": "fixed-dummy",
            "repo_url": "https://github.com/example/repo.git",
            "ref": "main",
            "flow_entrypoint": "src/dummy_engine/prefect_flow.py:dummy_engine_flow",
            "inputs": {},
            "env": {},
            "outputs_prefix": None,
        },
    )
    flow_run_id = out["id"]

    row = poll_flow_run(client, flow_run_id)
    summary = summarize_flow_run(row)
    print_json(summary)

    if summary["state_type"] != "COMPLETED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
