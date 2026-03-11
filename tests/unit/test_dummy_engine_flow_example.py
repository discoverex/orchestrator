from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DUMMY_ENGINE_SRC = ROOT_DIR / "tests" / "fixtures" / "dummy_engine_repo" / "src"
if str(DUMMY_ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(DUMMY_ENGINE_SRC))

from dummy_engine.prefect_flow import run_job_flow


def test_dummy_engine_flow_uses_orchestrator_contract_signature() -> None:
    params = run_job_flow.parameters.properties
    assert "job_spec_json" in params
    assert "resume_key" in params
    assert "checkpoint_dir" in params
