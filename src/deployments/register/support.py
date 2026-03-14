from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from common.prefect.deployment_targets import (
    DEFAULT_COLAB_DEPLOYMENT_NAME,
    DEFAULT_FIXED_DEPLOYMENT_NAME,
)

DEFAULT_FLOW_SOURCE = str(Path.cwd())
DEFAULT_SPEC_FILE = "deployments/e2e/e2e-deployments.yaml"
DEFAULT_RUNTIME_ENTRYPOINT = "src/flows/worker_runtime/flow.py:run_worker_job_flow"
DEFAULT_WRAPPER_ENTRYPOINT = DEFAULT_RUNTIME_ENTRYPOINT
DEFAULT_FIXED_DEPLOYMENT = DEFAULT_FIXED_DEPLOYMENT_NAME
DEFAULT_COLAB_DEPLOYMENT = DEFAULT_COLAB_DEPLOYMENT_NAME
DEFAULT_COMPAT_FIXED_DEPLOYMENT = "e2e-test-legacy"
DEFAULT_COMPAT_COLAB_DEPLOYMENT = "e2e-test-colab-legacy"


@dataclass(frozen=True)
class DeploymentSpec:
    name: str
    work_queue_name: str


@dataclass(frozen=True)
class RegistrationTarget:
    source: str
    entrypoint: str


@dataclass(frozen=True)
class CatalogDeployment:
    name: str
    work_queue_name: str
    mode: str
    role: str


@dataclass(frozen=True)
class RegistrationCatalog:
    entrypoint: str
    deployments: list[CatalogDeployment]


def build_base_parameters() -> dict[str, str]:
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


def iter_specs(args: argparse.Namespace) -> list[DeploymentSpec]:
    if args.single_name:
        return [DeploymentSpec(args.single_name, args.single_queue)]

    defaults: dict[str, CatalogDeployment] | None = None

    def _defaults() -> dict[str, CatalogDeployment]:
        nonlocal defaults
        if defaults is None:
            defaults = _catalog_defaults(load_catalog(args.spec_file))
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
    if args.register_compat_aliases:
        specs.extend(
            [
                DeploymentSpec(
                    args.compat_fixed_name or _defaults()["compat_fixed"].name,
                    args.compat_fixed_queue
                    or _defaults()["compat_fixed"].work_queue_name,
                ),
                DeploymentSpec(
                    args.compat_colab_name or _defaults()["compat_colab"].name,
                    args.compat_colab_queue
                    or _defaults()["compat_colab"].work_queue_name,
                ),
            ]
        )
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
    parser.add_argument(
        "--single-name", default=None, help="Single deployment name (compat mode)"
    )
    parser.add_argument(
        "--single-queue",
        default="default",
        help="Single deployment queue (compat mode)",
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
        "--compat-fixed-name",
        default=None,
        help="Compatibility alias for the fixed deployment",
    )
    parser.add_argument(
        "--compat-fixed-queue",
        default=None,
        help="Compatibility alias queue for the fixed deployment",
    )
    parser.add_argument(
        "--compat-colab-name",
        default=None,
        help="Compatibility alias for the colab deployment",
    )
    parser.add_argument(
        "--compat-colab-queue",
        default=None,
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


def load_catalog(spec_file: str) -> RegistrationCatalog:
    spec_path = Path(spec_file)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"deployment catalog must be a mapping: {spec_path}")

    flow = _require_mapping(raw, "flow", spec_path)
    flow_source = _require_str(flow, "source", spec_path)
    flow_entrypoint = _require_str(flow, "entrypoint", spec_path)
    entrypoint = (
        flow_entrypoint
        if ":" in flow_entrypoint
        else f"{flow_source}:{flow_entrypoint}"
    )

    deployments_node = raw.get("deployments")
    if not isinstance(deployments_node, list):
        raise ValueError(f"deployments must be a list: {spec_path}")

    deployments: list[CatalogDeployment] = []
    for item in deployments_node:
        if not isinstance(item, dict):
            raise ValueError(f"deployment entries must be mappings: {spec_path}")
        deployments.append(
            CatalogDeployment(
                name=_require_str(item, "name", spec_path),
                work_queue_name=_require_str(item, "work_queue", spec_path),
                mode=_require_str(item, "mode", spec_path),
                role=_require_str(item, "role", spec_path),
            )
        )
    return RegistrationCatalog(entrypoint=entrypoint, deployments=deployments)


def _catalog_defaults(
    catalog: RegistrationCatalog,
) -> dict[str, CatalogDeployment]:
    defaults: dict[str, CatalogDeployment] = {}
    for deployment in catalog.deployments:
        key = f"{_normalized_mode(deployment.mode)}_{deployment.role}"
        defaults[key] = deployment

    required = {
        "primary_fixed",
        "primary_colab",
        "compat_fixed",
        "compat_colab",
    }
    missing = sorted(required.difference(defaults))
    if missing:
        raise ValueError(f"deployment catalog missing roles: {', '.join(missing)}")
    return defaults


def _normalized_mode(mode: str) -> str:
    if mode == "compatibility":
        return "compat"
    return mode


def _require_mapping(
    data: dict[str, Any], key: str, spec_path: Path
) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping: {spec_path}")
    return value


def _require_str(data: dict[str, Any], key: str, spec_path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{key} must be a non-empty string: {spec_path}")
    return value
