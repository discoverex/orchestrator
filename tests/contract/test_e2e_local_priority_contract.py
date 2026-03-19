from __future__ import annotations

from pathlib import Path


def test_e2e_cli_help_mentions_priority_mode() -> None:
    content = Path("scripts/e2e/cli.sh").read_text(encoding="utf-8")

    assert "local [core|mlflow|priority]" in content


def test_local_e2e_usecase_routes_priority_mode() -> None:
    content = Path("scripts/e2e/usecases/local.sh").read_text(encoding="utf-8")

    assert "priority)" in content
    assert "e2e_local_prefect_priority.sh" in content


def test_priority_e2e_script_registers_two_single_queue_deployments() -> None:
    content = Path("scripts/e2e/e2e_local_prefect_priority.sh").read_text(
        encoding="utf-8"
    )

    assert "REGISTER_DEPLOYMENT_MODE=single" in content
    assert 'PREFECT_WORK_QUEUE="${PRIMARY_QUEUE}"' in content
    assert 'PREFECT_WORK_QUEUE="${BATCH_QUEUE}"' in content
    assert "verify-prefect-priority" in content
    assert "wait-prefect-state" in content
