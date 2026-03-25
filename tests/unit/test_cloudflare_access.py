from __future__ import annotations

import pytest
from fastapi import HTTPException

from common.cloudflare.access import normalize_host, require_service_token


def test_normalize_host_strips_port_and_case() -> None:
    assert normalize_host("Storage-API.Discoverex.QZZ.IO:443") == (
        "storage-api.discoverex.qzz.io"
    )


def test_require_service_token_bypasses_when_disabled() -> None:
    require_service_token(
        enabled=False,
        expected_id="",
        expected_secret="",
        provided_id=None,
        provided_secret=None,
    )


def test_require_service_token_requires_config_when_enabled() -> None:
    with pytest.raises(HTTPException, match="cf_access_not_configured") as exc_info:
        require_service_token(
            enabled=True,
            expected_id="",
            expected_secret="",
            provided_id="cf-id",
            provided_secret="cf-secret",
        )

    assert exc_info.value.status_code == 500


def test_require_service_token_rejects_invalid_credentials() -> None:
    with pytest.raises(HTTPException, match="cf_access_forbidden") as exc_info:
        require_service_token(
            enabled=True,
            expected_id="cf-id",
            expected_secret="cf-secret",
            provided_id="wrong",
            provided_secret="secret",
        )

    assert exc_info.value.status_code == 403
