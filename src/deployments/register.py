from __future__ import annotations

import argparse
from pathlib import Path

from prefect import flow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register Prefect deployment for engine_run_flow")
    parser.add_argument("--name", default="engine-run", help="Deployment name")
    parser.add_argument("--pool", default="colab-gpu", help="Prefect work pool name")
    parser.add_argument("--queue", default="default", help="Prefect work queue name")
    parser.add_argument("--version", default=None, help="Deployment version")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_flow = flow.from_source(
        source=str(Path.cwd()),
        entrypoint="src/flows/engine_run_flow.py:engine_run_flow",
    )
    source_flow.deploy(
        name=args.name,
        work_pool_name=args.pool,
        work_queue_name=args.queue,
        version=args.version,
        build=False,
        push=False,
        parameters={
            "repo_url": "https://github.com/example/repo.git",
            "ref": "main",
            "entrypoint": ["/bin/sh", "-lc", "echo hello"],
        },
    )


if __name__ == "__main__":
    main()
