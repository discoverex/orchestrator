from __future__ import annotations

from dummy_engine.main import main as run_dummy_engine
from prefect import flow


@flow(name="dummy-engine-job", retries=3, retry_delay_seconds=30)
def dummy_engine_flow(
    scene_id: str = "dummy-scene",
    version_id: str = "v1",
) -> dict[str, object]:
    run_dummy_engine()
    return {
        "status": "ok",
        "scene_id": scene_id,
        "version_id": version_id,
    }


run_job_flow = dummy_engine_flow
