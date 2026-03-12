from __future__ import annotations

from dummy_engine.prefect_flow import run_job_flow


def test_dummy_engine_flow_uses_orchestrator_contract_signature() -> None:
    params = run_job_flow.parameters.properties
    assert "job_spec_json" in params
    assert "resume_key" in params
    assert "checkpoint_dir" in params
