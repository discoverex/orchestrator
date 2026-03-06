from __future__ import annotations

import os

from fastapi import FastAPI

from storage.composition.container import build_storage_app_from_env
from storage_gateway.routes import build_router


def create_app() -> FastAPI:
    app = FastAPI(title="orchestrator-storage-gateway")
    app.state.storage_app = build_storage_app_from_env()
    app.state.token = os.getenv("STORAGE_GATEWAY_TOKEN", "dev-storage-token")
    app.state.require_cf_access = os.getenv("GATEWAY_REQUIRE_CF_ACCESS", "false").lower() in {"1", "true", "yes", "on"}
    app.state.cf_client_id = os.getenv("CF_ACCESS_CLIENT_ID", "")
    app.state.cf_client_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "")
    app.include_router(build_router(app))
    return app
