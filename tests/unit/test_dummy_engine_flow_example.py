from __future__ import annotations

from dummy_engine.prefect_flow import dummy_engine_flow


def test_dummy_engine_flow_uses_orchestrator_contract_signature() -> None:
    params = dummy_engine_flow.parameters.properties
    assert "scene_id" in params
    assert "version_id" in params
