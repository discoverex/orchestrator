from __future__ import annotations

import argparse
from typing import Any, Protocol, cast

from deployments.register.support import (
    DEFAULT_COLAB_DEPLOYMENT,
    DEFAULT_FIXED_DEPLOYMENT,
    DEFAULT_FLOW_SOURCE,
    DEFAULT_RUNTIME_ENTRYPOINT,
    DEFAULT_SPEC_FILE,
    DEFAULT_WRAPPER_ENTRYPOINT,
    build_base_parameters,
    build_parser,
    iter_specs,
    resolve_target,
)
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
        parameters: dict[str, Any],
    ) -> None: ...


__all__ = [
    "DEFAULT_COLAB_DEPLOYMENT",
    "DEFAULT_FIXED_DEPLOYMENT",
    "DEFAULT_FLOW_SOURCE",
    "DEFAULT_RUNTIME_ENTRYPOINT",
    "DEFAULT_SPEC_FILE",
    "DEFAULT_WRAPPER_ENTRYPOINT",
    "main",
    "parse_args",
]


def parse_args() -> argparse.Namespace:
    return build_parser().parse_args()


def main() -> None:
    args = parse_args()
    target = resolve_target(args)
    source_flow = cast(
        DeployableFlow,
        flow.from_source(
            source=target.source,
            entrypoint=target.entrypoint,
        ),
    )
    base_parameters = build_base_parameters(args.spec_file)
    for spec in iter_specs(args):
        source_flow.deploy(
            name=spec.name,
            work_pool_name=args.pool,
            work_queue_name=spec.work_queue_name,
            version=args.version,
            build=False,
            push=False,
            parameters=base_parameters,
        )


if __name__ == "__main__":
    main()
