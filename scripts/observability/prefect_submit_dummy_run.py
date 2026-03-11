#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.observability.lib.prefect_observe import (  # noqa: E402
    ROOT_DIR as OBSERVE_ROOT,
    build_client,
    load_job_spec,
    print_json,
    summarize_flow_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit a dummy flow run to a Prefect deployment."
    )
    parser.add_argument("--deployment-name", default="engine-run")
    parser.add_argument(
        "--job-spec-file",
        default=str(OBSERVE_ROOT / "scripts" / "e2e" / "fixed_dummy_inline_job.json"),
    )
    parser.add_argument("--flow-run-name", default="fixed-dummy-auth-flow-check")
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    deployment = client.find_deployment(args.deployment_name)
    created = client.create_flow_run(
        str(deployment["id"]),
        job_spec_raw=load_job_spec(args.job_spec_file),
        flow_run_name=args.flow_run_name,
    )
    print_json(summarize_flow_run(created))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
