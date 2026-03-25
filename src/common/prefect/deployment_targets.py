from __future__ import annotations

DEFAULT_FLOW_NAME = "e2e-job"
DEFAULT_FIXED_DEPLOYMENT_NAME = "e2e-test"
DEFAULT_COLAB_DEPLOYMENT_NAME = "e2e-test-colab"

DEFAULT_DUMMY_ENGINE_FLOW_NAME = "dummy-engine-job"
DEFAULT_DUMMY_ENGINE_FIXED_DEPLOYMENT_NAME = "discoverex-engine-run"
DEFAULT_DUMMY_ENGINE_COLAB_DEPLOYMENT_NAME = "discoverex-engine-run-colab"


def deployment_fqn(flow_name: str, deployment_name: str) -> str:
    return f"{flow_name}/{deployment_name}"


def default_fixed_deployment_fqn() -> str:
    return deployment_fqn(DEFAULT_FLOW_NAME, DEFAULT_FIXED_DEPLOYMENT_NAME)


def default_colab_deployment_fqn() -> str:
    return deployment_fqn(DEFAULT_FLOW_NAME, DEFAULT_COLAB_DEPLOYMENT_NAME)


def default_dummy_engine_fixed_deployment_fqn() -> str:
    return deployment_fqn(
        DEFAULT_DUMMY_ENGINE_FLOW_NAME,
        DEFAULT_DUMMY_ENGINE_FIXED_DEPLOYMENT_NAME,
    )


def default_dummy_engine_colab_deployment_fqn() -> str:
    return deployment_fqn(
        DEFAULT_DUMMY_ENGINE_FLOW_NAME,
        DEFAULT_DUMMY_ENGINE_COLAB_DEPLOYMENT_NAME,
    )


__all__ = [
    "DEFAULT_COLAB_DEPLOYMENT_NAME",
    "DEFAULT_DUMMY_ENGINE_COLAB_DEPLOYMENT_NAME",
    "DEFAULT_DUMMY_ENGINE_FIXED_DEPLOYMENT_NAME",
    "DEFAULT_DUMMY_ENGINE_FLOW_NAME",
    "DEFAULT_FIXED_DEPLOYMENT_NAME",
    "DEFAULT_FLOW_NAME",
    "default_colab_deployment_fqn",
    "default_dummy_engine_colab_deployment_fqn",
    "default_dummy_engine_fixed_deployment_fqn",
    "default_fixed_deployment_fqn",
    "deployment_fqn",
]
