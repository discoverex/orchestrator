from __future__ import annotations

from dummy_engine.prefect_flow import dummy_engine_flow


def test_dummy_engine_flow_uses_orchestrator_contract_signature() -> None:
    params = dummy_engine_flow.parameters.properties
    assert "run_mode" in params
    assert "engine" in params
    assert "entrypoint" in params
    assert "resume_key" in params
    assert "checkpoint_dir" in params
