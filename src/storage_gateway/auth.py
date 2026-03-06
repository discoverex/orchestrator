from __future__ import annotations

from typing import Callable, Protocol

from fastapi import FastAPI
from fastapi import Header, HTTPException


class GatewayAuthState(Protocol):
    token: str
    require_cf_access: bool
    cf_client_id: str
    cf_client_secret: str


def authorize(
    app_state: GatewayAuthState,
    authorization: str | None,
    cf_access_client_id: str | None,
    cf_access_client_secret: str | None,
) -> None:
    expected = f"Bearer {app_state.token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not app_state.require_cf_access:
        return
    if not app_state.cf_client_id or not app_state.cf_client_secret:
        raise HTTPException(status_code=500, detail="cf_access_not_configured")
    if cf_access_client_id != app_state.cf_client_id or cf_access_client_secret != app_state.cf_client_secret:
        raise HTTPException(status_code=403, detail="cf_access_forbidden")


def authorize_dependency(app: FastAPI) -> Callable[[str | None, str | None, str | None], None]:
    def _authorize(
        authorization: str | None = Header(default=None),
        cf_access_client_id: str | None = Header(default=None),
        cf_access_client_secret: str | None = Header(default=None),
    ) -> None:
        authorize(app.state, authorization, cf_access_client_id, cf_access_client_secret)

    return _authorize
