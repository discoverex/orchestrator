from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    # write-summary-local
    p = subparsers.add_parser("write-summary-local")
    p.add_argument("--steps-file", required=True)
    p.add_argument("--summary-file", required=True)
    p.add_argument("--mode", required=True)
    p.add_argument("--flow-run-id", default="")
    p.add_argument("--mlflow-run-id", default="")

    # poll-prefect-completion
    p = subparsers.add_parser("poll-prefect-completion")
    p.add_argument("--prefect-api-url", required=True)
    p.add_argument("--flow-run-id", required=True)
    p.add_argument("--timeout-sec", type=int, default=300)

    # verify-storage-objects
    p = subparsers.add_parser("verify-storage-objects")
    p.add_argument("--storage-api-url", required=True)
    p.add_argument("--flow-run-id", required=True)
    p.add_argument("--attempt", type=int, required=True)
    p.add_argument("--artifact-bucket", required=True)
    p.add_argument("--presigned-internal-base-url", default="")
    p.add_argument("--presigned-host-header", default="")
    p.add_argument("--cf-access-client-id", default="")
    p.add_argument("--cf-access-client-secret", default="")
    p.add_argument("--skip-engine-artifacts", action="store_true")
    p.add_argument("--log-dir", default=".")

    # verify-engine-mlflow-run
    p = subparsers.add_parser("verify-engine-mlflow-run")
    p.add_argument("--mlflow-tracking-uri", required=True)
    p.add_argument("--mlflow-experiment-name", required=True)
    p.add_argument("--scene-version", required=True)
    p.add_argument("--flow-run-id", required=True)
    p.add_argument("--cf-access-client-id", default="")
    p.add_argument("--cf-access-client-secret", default="")

    # create-and-verify-mlflow-tags
    p = subparsers.add_parser("create-and-verify-mlflow-tags")
    p.add_argument("--mlflow-tracking-uri", required=True)
    p.add_argument("--mlflow-run-id", required=True)
    p.add_argument("--cf-access-client-id", default="")
    p.add_argument("--cf-access-client-secret", default="")

    # uri-host
    p = subparsers.add_parser("uri-host")
    p.add_argument("uri")

    # verify-flush-output
    p = subparsers.add_parser("verify-flush-output")
    p.add_argument("--output-json", required=True)
    p.add_argument("--flow-run-id", required=True)

    # verify-prune-removed
    p = subparsers.add_parser("verify-prune-removed")
    p.add_argument("--storage-api-url", required=True)
    p.add_argument("--flow-run-id", required=True)
    p.add_argument("--attempt", type=int, required=True)
    p.add_argument("--cf-access-client-id", default="")
    p.add_argument("--cf-access-client-secret", default="")

    # write-summary-remote
    p = subparsers.add_parser("write-summary-remote")
    p.add_argument("--steps-file", required=True)
    p.add_argument("--summary-file", required=True)
    p.add_argument("--flow-run-id", required=True)
    p.add_argument("--prefect-api-url", required=True)
    p.add_argument("--work-pool", required=True)
    p.add_argument("--work-queue", required=True)
    p.add_argument("--prune-mode", required=True)

    # build-cf-headers-json
    p = subparsers.add_parser("build-cf-headers-json")
    p.add_argument("--client-id", default="")
    p.add_argument("--client-secret", default="")

    return parser
