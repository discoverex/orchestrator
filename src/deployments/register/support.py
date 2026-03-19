from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from common.prefect.deployment_targets import (
    DEFAULT_COLAB_DEPLOYMENT_NAME,
    DEFAULT_FIXED_DEPLOYMENT_NAME,
)
from deployments.register.catalog import (
    CatalogDeployment,
    catalog_defaults,
    load_catalog,
)

DEFAULT_FLOW_SOURCE = str(Path.cwd())
DEFAULT_SPEC_FILE = "deployments/e2e/e2e-deployments.yaml"
DEFAULT_RUNTIME_ENTRYPOINT = "src/flows/worker_runtime/flow.py:run_worker_job_flow"
DEFAULT_WRAPPER_ENTRYPOINT = DEFAULT_RUNTIME_ENTRYPOINT
DEFAULT_FIXED_DEPLOYMENT = DEFAULT_FIXED_DEPLOYMENT_NAME
DEFAULT_COLAB_DEPLOYMENT = DEFAULT_COLAB_DEPLOYMENT_NAME


@dataclass(frozen=True)
class DeploymentSpec:
    name: str
    work_queue_name: str


@dataclass(frozen=True)
class RegistrationTarget:
    source: str
    entrypoint: str


def build_base_parameters(spec_file: str) -> dict[str, object]:
    return deepcopy(load_catalog(spec_file).parameters)


def iter_specs(args: argparse.Namespace) -> list[DeploymentSpec]:
    if args.single_name:
        return [DeploymentSpec(args.single_name, args.single_queue)]

    defaults: dict[str, CatalogDeployment] | None = None

    def _defaults() -> dict[str, CatalogDeployment]:
        nonlocal defaults
        if defaults is None:
            defaults = catalog_defaults(load_catalog(args.spec_file))
        return defaults

    specs = [
        DeploymentSpec(
            args.fixed_name or _defaults()["primary_fixed"].name,
            args.fixed_queue or _defaults()["primary_fixed"].work_queue_name,
        ),
        DeploymentSpec(
            args.colab_name or _defaults()["primary_colab"].name,
            args.colab_queue or _defaults()["primary_colab"].work_queue_name,
        ),
    ]
    return _dedupe_specs(specs)


def resolve_target(args: argparse.Namespace) -> RegistrationTarget:
    return RegistrationTarget(
        source=args.flow_source,
        entrypoint=args.flow_entrypoint or load_catalog(args.spec_file).entrypoint,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Register Prefect deployments for orchestrator or engine flows."
    )
    parser.add_argument("--single-name", default=None, help="Single deployment name")
    parser.add_argument(
        "--single-queue",
        default="default",
        help="Single deployment queue",
    )
    parser.add_argument(
        "--spec-file",
        default=DEFAULT_SPEC_FILE,
        help="YAML deployment catalog used as the registration source of truth",
    )
    parser.add_argument("--pool", default="gpu-pool", help="Prefect work pool name")
    parser.add_argument(
        "--fixed-name",
        default=None,
        help="Primary fixed deployment name",
    )
    parser.add_argument(
        "--fixed-queue", default=None, help="Primary fixed deployment queue"
    )
    parser.add_argument(
        "--colab-name",
        default=None,
        help="Primary colab deployment name",
    )
    parser.add_argument(
        "--colab-queue", default=None, help="Primary colab deployment queue"
    )
    parser.add_argument(
        "--flow-source",
        default=DEFAULT_FLOW_SOURCE,
        help="Flow source root passed to Prefect flow.from_source()",
    )
    parser.add_argument(
        "--flow-entrypoint",
        default=None,
        help="Flow entrypoint passed to Prefect flow.from_source()",
    )
    parser.add_argument("--version", default=None, help="Deployment version")
    return parser


def _dedupe_specs(specs: list[DeploymentSpec]) -> list[DeploymentSpec]:
    deduped: list[DeploymentSpec] = []
    seen: set[tuple[str, str]] = set()
    for spec in specs:
        key = (spec.name, spec.work_queue_name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(spec)
    return deduped
