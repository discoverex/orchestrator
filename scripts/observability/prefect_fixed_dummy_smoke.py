#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.observability.lib.prefect_observe import (  # noqa: E402
    ROOT_DIR as OBSERVE_ROOT,
)
from scripts.observability.lib.prefect_observe import (  # noqa: E402
    build_client,
    load_job_spec,
    poll_flow_run,
    print_json,
    summarize_deployment,
    summarize_flow_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run fixed deployment auth/deployment/dummy flow smoke check."
    )
    parser.add_argument("--deployment-name", default="discoverex-engine-run")
    parser.add_argument(
        "--job-spec-file",
        default=str(OBSERVE_ROOT / "scripts" / "e2e" / "fixed_dummy_inline_job.json"),
    )
    parser.add_argument("--flow-run-name", default="fixed-standard-dummy-smoke")
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--poll-interval-sec", type=int, default=5)
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()

    client = build_client(args.env_file)
    deployment = client.find_deployment(args.deployment_name)
    created = client.create_flow_run(
        str(deployment["id"]),
        job_spec_raw=load_job_spec(args.job_spec_file),
        flow_run_name=args.flow_run_name,
    )
    final = poll_flow_run(
        client,
        str(created["id"]),
        timeout_sec=args.timeout_sec,
        poll_interval_sec=args.poll_interval_sec,
    )

    result = {
        "health_ok": client.health(),
        "deployment": summarize_deployment(deployment),
        "created_flow_run": summarize_flow_run(created),
        "final_flow_run": summarize_flow_run(final),
    }
    print_json(result)
    state_type = str(
        cast(dict[str, object], result["final_flow_run"]).get("state_type") or ""
    ).upper()
    return 0 if state_type == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
