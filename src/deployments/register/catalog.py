from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


@dataclass(frozen=True)
class CatalogDeployment:
    name: str
    work_queue_name: str
    mode: str
    role: str


@dataclass(frozen=True)
class RegistrationCatalog:
    entrypoint: str
    parameters: dict[str, object]
    deployments: list[CatalogDeployment]


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
    parameters = _load_parameters(flow, spec_path)
    deployments = _load_deployments(raw, spec_path)
    return RegistrationCatalog(
        entrypoint=entrypoint,
        parameters=parameters,
        deployments=deployments,
    )


def _load_parameters(flow: dict[str, Any], spec_path: Path) -> dict[str, object]:
    value = flow.get("parameters")
    if value is None:
        raise ValueError(f"flow.parameters must be provided: {spec_path}")
    if not isinstance(value, dict):
        raise ValueError(f"flow.parameters must be a mapping: {spec_path}")
    return value


def catalog_defaults(catalog: RegistrationCatalog) -> dict[str, CatalogDeployment]:
    defaults = {
        f"{deployment.mode}_{deployment.role}": deployment
        for deployment in catalog.deployments
    }
    required = {"primary_fixed", "primary_colab"}
    missing = sorted(required.difference(defaults))
    if missing:
        raise ValueError(f"deployment catalog missing roles: {', '.join(missing)}")
    return defaults


def _load_deployments(raw: dict[str, Any], spec_path: Path) -> list[CatalogDeployment]:
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
    return deployments


def _require_mapping(data: dict[str, Any], key: str, spec_path: Path) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping: {spec_path}")
    return value


def _require_str(data: dict[str, Any], key: str, spec_path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{key} must be a non-empty string: {spec_path}")
    return value
