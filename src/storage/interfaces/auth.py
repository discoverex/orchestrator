from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from fastapi import FastAPI, Header

from common.cloudflare.access import require_service_token


class StorageAuthState(Protocol):
    require_cf_access: bool
    cf_client_id: str
    cf_client_secret: str


def authorize(
    app_state: StorageAuthState,
    cf_access_client_id: str | None,
    cf_access_client_secret: str | None,
) -> None:
    require_service_token(
        enabled=app_state.require_cf_access,
        expected_id=app_state.cf_client_id,
        expected_secret=app_state.cf_client_secret,
        provided_id=cf_access_client_id,
        provided_secret=cf_access_client_secret,
    )


def authorize_dependency(
    app: FastAPI,
) -> Callable[[str | None, str | None], None]:
    def _authorize(
        cf_access_client_id: str | None = Header(default=None),
        cf_access_client_secret: str | None = Header(default=None),
    ) -> None:
        authorize(app.state, cf_access_client_id, cf_access_client_secret)

    return _authorize
