from __future__ import annotations

from pathlib import Path


def test_prefect_db_url_uses_runtime_env_substitution() -> None:
    compose = Path("infra/stacks/prefect-server/docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "$${PREFECT_DB_USER}" in compose
    assert "$${PREFECT_DB_PASSWORD}" in compose
    assert "$${PREFECT_DB_NAME}" in compose
