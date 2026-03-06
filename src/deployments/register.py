from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Protocol, cast

from prefect import flow


class DeployableFlow(Protocol):
    def deploy(
        self,
        *,
        name: str,
        work_pool_name: str,
        work_queue_name: str,
        version: str | None,
        build: bool,
        push: bool,
        parameters: dict[str, str],
    ) -> None: ...


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register Prefect deployment for engine_run_flow"
    )
    parser.add_argument(
        "--single-name", default=None, help="Single deployment name (compat mode)"
    )
    parser.add_argument(
        "--single-queue",
        default="default",
        help="Single deployment queue (compat mode)",
    )
    parser.add_argument("--pool", default="gpu-pool", help="Prefect work pool name")
    parser.add_argument(
        "--fixed-name", default="engine-run", help="Fixed deployment name"
    )
    parser.add_argument(
        "--fixed-queue", default="gpu-fixed", help="Fixed deployment queue"
    )
    parser.add_argument(
        "--colab-name", default="engine-run-colab", help="Colab deployment name"
    )
    parser.add_argument(
        "--colab-queue", default="gpu-colab", help="Colab deployment queue"
    )
    parser.add_argument("--version", default=None, help="Deployment version")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_flow = cast(
        DeployableFlow,
        flow.from_source(
            source=str(Path.cwd()),
            entrypoint="src/flows/engine_run_flow.py:engine_run_flow",
        ),
    )
    base_parameters = {
        "job_spec_json": json.dumps(
            {
                "engine": "shell",
                "repo_url": "https://github.com/example/repo.git",
                "ref": "main",
                "entrypoint": ["/bin/sh", "-lc", "echo hello"],
                "config": None,
                "job_name": None,
                "inputs": {},
                "env": {},
                "outputs_prefix": None,
            },
            ensure_ascii=True,
        )
    }

    if args.single_name:
        source_flow.deploy(
            name=args.single_name,
            work_pool_name=args.pool,
            work_queue_name=args.single_queue,
            version=args.version,
            build=False,
            push=False,
            parameters=base_parameters,
        )
        return

    source_flow.deploy(
        name=args.fixed_name,
        work_pool_name=args.pool,
        work_queue_name=args.fixed_queue,
        version=args.version,
        build=False,
        push=False,
        parameters=base_parameters,
    )
    source_flow.deploy(
        name=args.colab_name,
        work_pool_name=args.pool,
        work_queue_name=args.colab_queue,
        version=args.version,
        build=False,
        push=False,
        parameters=base_parameters,
    )


if __name__ == "__main__":
    main()
