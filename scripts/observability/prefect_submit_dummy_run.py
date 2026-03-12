#!/usr/bin/env python3
from __future__ import annotations

import argparse

from scripts.observability.lib.prefect_observe_env import (
    build_client,
    load_job_spec,
)
from scripts.observability.lib.prefect_observe_format import (
    print_json,
    summarize_flow_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit a dummy flow run to a Prefect deployment."
    )
    parser.add_argument(
        "--deployment-name",
        default="e2e-job/e2e-test",
        help="Target deployment name (flow/deployment)",
    )
    parser.add_argument("--job-spec-file", default=None)
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    deployment = client.find_deployment(args.deployment_name)
    job_spec_raw = load_job_spec(args.job_spec_file)

    out = client.create_flow_run(deployment["id"], job_spec_raw=job_spec_raw)
    print_json(summarize_flow_run(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
