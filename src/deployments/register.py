from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from prefect import flow

DEFAULT_FLOW_SOURCE = str(Path.cwd())
DEFAULT_WRAPPER_ENTRYPOINT = "src/flows/engine_run_flow.py:engine_run_flow"
DEFAULT_FIXED_DEPLOYMENT = "discoverex-engine-run"
DEFAULT_COLAB_DEPLOYMENT = "discoverex-engine-run-colab"
DEFAULT_COMPAT_FIXED_DEPLOYMENT = "engine-run"
DEFAULT_COMPAT_COLAB_DEPLOYMENT = "engine-run-colab"


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


@dataclass(frozen=True)
class DeploymentSpec:
    name: str
    work_queue_name: str


@dataclass(frozen=True)
class RegistrationTarget:
    source: str
    entrypoint: str


def _base_parameters() -> dict[str, str]:
    return {
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


def _iter_specs(args: argparse.Namespace) -> list[DeploymentSpec]:
    if args.single_name:
        return [
            DeploymentSpec(
                name=args.single_name,
                work_queue_name=args.single_queue,
            )
        ]

    specs = [
        DeploymentSpec(name=args.fixed_name, work_queue_name=args.fixed_queue),
        DeploymentSpec(name=args.colab_name, work_queue_name=args.colab_queue),
    ]
    if args.register_compat_aliases:
        specs.extend(
            [
                DeploymentSpec(
                    name=args.compat_fixed_name,
                    work_queue_name=args.compat_fixed_queue,
                ),
                DeploymentSpec(
                    name=args.compat_colab_name,
                    work_queue_name=args.compat_colab_queue,
                ),
            ]
        )

    deduped: list[DeploymentSpec] = []
    seen: set[tuple[str, str]] = set()
    for spec in specs:
        key = (spec.name, spec.work_queue_name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(spec)
    return deduped


def _resolve_target(args: argparse.Namespace) -> RegistrationTarget:
    return RegistrationTarget(source=args.flow_source, entrypoint=args.flow_entrypoint)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register Prefect deployments for orchestrator or engine flows."
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
        "--fixed-name",
        default=DEFAULT_FIXED_DEPLOYMENT,
        help="Primary fixed deployment name",
    )
    parser.add_argument(
        "--fixed-queue", default="gpu-fixed", help="Primary fixed deployment queue"
    )
    parser.add_argument(
        "--colab-name",
        default=DEFAULT_COLAB_DEPLOYMENT,
        help="Primary colab deployment name",
    )
    parser.add_argument(
        "--colab-queue", default="gpu-colab", help="Primary colab deployment queue"
    )
    parser.add_argument(
        "--compat-fixed-name",
        default=DEFAULT_COMPAT_FIXED_DEPLOYMENT,
        help="Compatibility alias for the fixed deployment",
    )
    parser.add_argument(
        "--compat-fixed-queue",
        default="gpu-fixed",
        help="Compatibility alias queue for the fixed deployment",
    )
    parser.add_argument(
        "--compat-colab-name",
        default=DEFAULT_COMPAT_COLAB_DEPLOYMENT,
        help="Compatibility alias for the colab deployment",
    )
    parser.add_argument(
        "--compat-colab-queue",
        default="gpu-colab",
        help="Compatibility alias queue for the colab deployment",
    )
    parser.add_argument(
        "--register-compat-aliases",
        dest="register_compat_aliases",
        action="store_true",
        help="Register legacy engine-run aliases alongside the primary deployments",
    )
    parser.add_argument(
        "--no-register-compat-aliases",
        dest="register_compat_aliases",
        action="store_false",
        help="Skip legacy engine-run compatibility aliases",
    )
    parser.set_defaults(register_compat_aliases=True)
    parser.add_argument(
        "--flow-source",
        default=DEFAULT_FLOW_SOURCE,
        help="Flow source root passed to Prefect flow.from_source()",
    )
    parser.add_argument(
        "--flow-entrypoint",
        default=DEFAULT_WRAPPER_ENTRYPOINT,
        help="Flow entrypoint passed to Prefect flow.from_source()",
    )
    parser.add_argument("--version", default=None, help="Deployment version")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target = _resolve_target(args)
    source_flow = cast(
        DeployableFlow,
        flow.from_source(
            source=target.source,
            entrypoint=target.entrypoint,
        ),
    )
    base_parameters = _base_parameters()
    for spec in _iter_specs(args):
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
