#!/usr/bin/env python3
from __future__ import annotations

import argparse

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
        default="e2e-job/e2e-test",
        help="Target deployment name (flow/deployment)",
    )
    args = parser.parse_args()

    client = build_client(args.env_file)
    deployment = client.find_deployment(args.deployment_name)

    job_spec_raw = '{"run_mode": "inline", "engine": "fixed-dummy"}'
    out = client.create_flow_run(deployment["id"], job_spec_raw=job_spec_raw)
    flow_run_id = out["id"]

    row = poll_flow_run(client, flow_run_id)
    summary = summarize_flow_run(row)
    print_json(summary)

    if summary["state_type"] != "COMPLETED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
