from fastapi import APIRouter, FastAPI, Header, Request, Response, WebSocket

from storage.composition.container import build_storage_app_from_env
from storage.interfaces import build_artifact_router
from worker_router import auth as _auth
from worker_router import proxy as _proxy_mod
from worker_router import websocket_proxy as _websocket_proxy_mod

_authorize_storage_request = _auth.authorize_storage_request
_check_gateway_auth = _auth.check_gateway_auth
_router_is_local_only = _auth.router_is_local_only
_storage_host_mode = _auth.storage_host_mode
_mlflow_upstream = _proxy_mod.mlflow_upstream
_prefect_upstream = _proxy_mod.prefect_upstream
_proxy = _proxy_mod.proxy_request
_proxy_websocket = _websocket_proxy_mod.proxy_websocket


def create_app() -> FastAPI:
    app = FastAPI(title="orchestrator-worker-router")
    router = APIRouter()
    mlflow = _mlflow_upstream()
    prefect = _prefect_upstream()
    storage_app = build_storage_app_from_env()
    app.state.storage_app = storage_app

    @router.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.api_route(
        "/mlflow/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
    )
    async def mlflow_proxy(
        path: str,
        request_in: Request,
        cf_access_client_id: str | None = Header(default=None),
        cf_access_client_secret: str | None = Header(default=None),
    ) -> Response:
        if not _router_is_local_only():
            _check_gateway_auth(cf_access_client_id, cf_access_client_secret)
        return await _proxy(request_in, mlflow, path)

    @router.api_route(
        "/prefect/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
    )
    async def prefect_proxy(
        path: str,
        request_in: Request,
        cf_access_client_id: str | None = Header(default=None),
        cf_access_client_secret: str | None = Header(default=None),
    ) -> Response:
        if not prefect.base_url:
            return Response(
                content=(
                    b'{"upstream":"prefect",'
                    b'"detail":"missing PREFECT_UPSTREAM_URL"}'
                ),
                status_code=503,
                media_type="application/json",
            )
        if not _router_is_local_only():
            _check_gateway_auth(cf_access_client_id, cf_access_client_secret)
        return await _proxy(request_in, prefect, path)

    @router.websocket("/prefect/{path:path}")
    async def prefect_proxy_websocket(websocket: WebSocket, path: str) -> None:
        await _proxy_websocket(websocket, prefect, path)

    app.include_router(router)
    app.include_router(
        build_artifact_router(
            storage_app,
            _authorize_storage_request,
            prefix="/artifact",
        )
    )
    return app
