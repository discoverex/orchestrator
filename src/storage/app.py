from __future__ import annotations

import os

from fastapi import FastAPI

from storage.composition.container import build_storage_app_from_env
from storage.interfaces.auth import authorize
from storage.interfaces.http import build_artifact_router


def create_app() -> FastAPI:
    app = FastAPI(title="orchestrator-storage")
    app.state.storage_app = build_storage_app_from_env()
    app.state.require_cf_access = os.getenv(
        "GATEWAY_REQUIRE_CF_ACCESS", "false"
    ).lower() in {"1", "true", "yes", "on"}
    app.state.cf_client_id = os.getenv("CF_ACCESS_CLIENT_ID", "")
    app.state.cf_client_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "")

    def authorize_request(
        _request: object,
        cf_access_client_id: str | None,
        cf_access_client_secret: str | None,
    ) -> None:
        authorize(app.state, cf_access_client_id, cf_access_client_secret)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(build_artifact_router(app.state.storage_app, authorize_request))
    return app
