from __future__ import annotations

import html
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, quote_plus

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field


class ExplorerSessionRequest(BaseModel):
    token: str = Field(min_length=1)


class ExplorerSessionResponse(BaseModel):
    status: str


class ExplorerBucketsResponse(BaseModel):
    buckets: list[str]


class ExplorerObjectEntry(BaseModel):
    object_uri: str
    object_key: str
    size: int
    last_modified: str | None
    is_dir: bool


class ExplorerObjectsResponse(BaseModel):
    bucket: str
    prefix: str
    next_cursor: str | None
    entries: list[ExplorerObjectEntry]


def build_explorer_router(app) -> APIRouter:
    router = APIRouter(tags=["explorer"])

    def _assert_enabled() -> None:
        if not app.state.explorer_enabled:
            raise HTTPException(status_code=404, detail="explorer_disabled")

    def _assert_local_request(request: Request) -> None:
        _assert_enabled()
        if not app.state.explorer_local_only:
            return
        host = request.client.host if request.client else ""
        if host not in app.state.explorer_local_hosts:
            raise HTTPException(status_code=403, detail="local_only")

    def _prune_sessions() -> None:
        now = datetime.now(timezone.utc)
        expired = [sid for sid, exp in app.state.explorer_sessions.items() if exp <= now]
        for sid in expired:
            app.state.explorer_sessions.pop(sid, None)

    def _require_session(request: Request) -> str:
        _assert_local_request(request)
        _prune_sessions()
        sid = request.cookies.get(app.state.explorer_cookie_name)
        if not sid:
            raise HTTPException(status_code=401, detail="missing_explorer_session")
        exp = app.state.explorer_sessions.get(sid)
        if exp is None or exp <= datetime.now(timezone.utc):
            app.state.explorer_sessions.pop(sid, None)
            raise HTTPException(status_code=401, detail="invalid_explorer_session")
        app.state.explorer_sessions[sid] = datetime.now(timezone.utc) + timedelta(seconds=app.state.explorer_session_ttl)
        return sid

    def _create_session() -> str:
        sid = secrets.token_urlsafe(24)
        app.state.explorer_sessions[sid] = datetime.now(timezone.utc) + timedelta(seconds=app.state.explorer_session_ttl)
        return sid

    def _list_objects(bucket: str, prefix: str, cursor: str | None, limit: int) -> ExplorerObjectsResponse:
        rows = app.state.storage_app.list_objects(bucket=bucket, prefix=prefix, cursor=cursor, limit=limit)
        return ExplorerObjectsResponse(
            bucket=rows.bucket,
            prefix=rows.prefix,
            next_cursor=rows.next_cursor,
            entries=[
                ExplorerObjectEntry(
                    object_uri=row.object_uri,
                    object_key=row.object_key,
                    size=row.size,
                    last_modified=row.last_modified.isoformat() if row.last_modified else None,
                    is_dir=row.object_key.endswith("/"),
                )
                for row in rows.entries
            ],
        )

    @router.post("/v1/explorer/session", response_model=ExplorerSessionResponse)
    def create_session(payload: ExplorerSessionRequest, request: Request, response: Response) -> ExplorerSessionResponse:
        _assert_local_request(request)
        if payload.token != app.state.token:
            raise HTTPException(status_code=401, detail="unauthorized")
        sid = _create_session()
        response.set_cookie(
            key=app.state.explorer_cookie_name,
            value=sid,
            httponly=True,
            samesite="lax",
            max_age=app.state.explorer_session_ttl,
        )
        return ExplorerSessionResponse(status="ok")

    @router.delete("/v1/explorer/session", response_model=ExplorerSessionResponse)
    def delete_session(request: Request, response: Response) -> ExplorerSessionResponse:
        _assert_local_request(request)
        sid = request.cookies.get(app.state.explorer_cookie_name)
        if sid:
            app.state.explorer_sessions.pop(sid, None)
        response.delete_cookie(app.state.explorer_cookie_name)
        return ExplorerSessionResponse(status="ok")

    @router.get("/v1/explorer/buckets", response_model=ExplorerBucketsResponse)
    def list_buckets(request: Request) -> ExplorerBucketsResponse:
        _require_session(request)
        return ExplorerBucketsResponse(buckets=app.state.storage_app.list_buckets())

    @router.get("/v1/explorer/objects", response_model=ExplorerObjectsResponse)
    def list_objects(
        request: Request,
        bucket: str = Query(min_length=1),
        prefix: str = Query(default=""),
        cursor: str | None = Query(default=None),
        limit: int | None = Query(default=None, ge=1, le=1000),
    ) -> ExplorerObjectsResponse:
        _require_session(request)
        page_size = limit or app.state.explorer_page_size
        return _list_objects(bucket=bucket, prefix=prefix, cursor=cursor, limit=page_size)

    @router.get("/v1/explorer/download")
    def download_object(request: Request, object_uri: str = Query(min_length=6)) -> Response:
        _require_session(request)
        data = app.state.storage_app.download_object(object_uri)
        filename = object_uri.rsplit("/", 1)[-1] or "artifact.bin"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content=data, media_type="application/octet-stream", headers=headers)

    def _render_login(error: str | None = None) -> str:
        error_html = f"<p style='color:#b00020'>{html.escape(error)}</p>" if error else ""
        return (
            "<!doctype html><html><head><meta charset='utf-8'><title>Storage Explorer Login</title>"
            "<style>body{font-family:ui-monospace,Menlo,Consolas,monospace;max-width:760px;margin:40px auto;padding:0 16px;}"
            "input,button{font:inherit;padding:8px;}form{display:flex;gap:8px;align-items:center;}</style></head><body>"
            "<h1>Storage Explorer (Local)</h1>"
            "<p>Enter storage gateway token to start a local session.</p>"
            f"{error_html}"
            "<form method='post' action='/explorer/login'>"
            "<input type='password' name='token' placeholder='STORAGE_GATEWAY_TOKEN' style='min-width:360px' required />"
            "<button type='submit'>Login</button>"
            "</form></body></html>"
        )

    def _parent_prefix(prefix: str) -> str:
        clean = prefix.rstrip("/")
        if not clean:
            return ""
        parts = clean.split("/")
        if len(parts) <= 1:
            return ""
        return "/".join(parts[:-1]) + "/"

    def _render_explorer(bucket: str, prefix: str, buckets: list[str], rows: ExplorerObjectsResponse, error: str | None = None) -> str:
        bucket_options = "".join(
            f"<option value='{html.escape(b)}' {'selected' if b == bucket else ''}>{html.escape(b)}</option>" for b in buckets
        )
        items = []
        if prefix:
            parent = _parent_prefix(prefix)
            items.append(
                "<tr><td><a href='/explorer?bucket="
                f"{quote_plus(bucket)}&prefix={quote_plus(parent)}'>..</a></td><td></td><td></td><td></td></tr>"
            )
        for e in rows.entries:
            key_label = html.escape(e.object_key)
            if e.is_dir:
                href = f"/explorer?bucket={quote_plus(bucket)}&prefix={quote_plus(e.object_key)}"
                # Directory rows are navigated from the filename link itself.
                key_cell = f"<a href='{href}'>[DIR] {key_label}</a>"
                action = "-"
            else:
                key_cell = key_label
                action = (
                    "<a href='/v1/explorer/download?object_uri="
                    f"{quote_plus(e.object_uri)}'><button type='button'>Download</button></a>"
                )
            items.append(
                "<tr>"
                f"<td>{key_cell}</td>"
                f"<td>{e.size}</td>"
                f"<td>{html.escape(e.last_modified or '-')}</td>"
                f"<td>{action}</td>"
                "</tr>"
            )
        rows_html = "".join(items) or "<tr><td colspan='4'>No objects</td></tr>"
        next_html = ""
        if rows.next_cursor:
            next_html = (
                "<a href='/explorer?bucket="
                f"{quote_plus(bucket)}&prefix={quote_plus(prefix)}&cursor={quote_plus(rows.next_cursor)}'>Next page</a>"
            )
        error_html = f"<p style='color:#b00020'>{html.escape(error)}</p>" if error else ""
        return (
            "<!doctype html><html><head><meta charset='utf-8'><title>Storage Explorer</title>"
            "<style>body{font-family:ui-monospace,Menlo,Consolas,monospace;max-width:1100px;margin:20px auto;padding:0 16px;}"
            "table{width:100%;border-collapse:collapse;}td,th{border-bottom:1px solid #ddd;padding:8px;text-align:left;}"
            "form.inline{display:inline;} .bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}</style></head><body>"
            "<div class='bar'><h1 style='margin-right:auto'>Storage Explorer (Local)</h1>"
            "<form class='inline' method='post' action='/explorer/logout'><button type='submit'>Logout</button></form></div>"
            f"{error_html}"
            "<form method='get' action='/explorer' class='bar'>"
            f"<select name='bucket'>{bucket_options}</select>"
            f"<input type='text' name='prefix' value='{html.escape(prefix)}' placeholder='prefix/' style='min-width:360px'/>"
            "<button type='submit'>Browse</button></form>"
            f"<p><strong>Bucket:</strong> {html.escape(bucket)} | <strong>Prefix:</strong> {html.escape(prefix or '/')}</p>"
            "<table><thead><tr><th>Key</th><th>Size</th><th>Last Modified</th><th>Action</th></tr></thead><tbody>"
            f"{rows_html}</tbody></table><div style='margin-top:12px'>{next_html}</div></body></html>"
        )

    @router.get("/explorer", response_class=HTMLResponse)
    def explorer_page(
        request: Request,
        bucket: str | None = Query(default=None),
        prefix: str = Query(default=""),
        cursor: str | None = Query(default=None),
    ) -> HTMLResponse:
        _assert_local_request(request)
        try:
            _require_session(request)
        except HTTPException:
            return HTMLResponse(_render_login())

        buckets = app.state.storage_app.list_buckets()
        selected_bucket = bucket or (buckets[0] if buckets else "")
        if not selected_bucket:
            return HTMLResponse(_render_explorer("", prefix, buckets, ExplorerObjectsResponse(bucket="", prefix=prefix, next_cursor=None, entries=[])))

        try:
            rows = _list_objects(bucket=selected_bucket, prefix=prefix, cursor=cursor, limit=app.state.explorer_page_size)
            return HTMLResponse(_render_explorer(selected_bucket, prefix, buckets, rows))
        except Exception as exc:  # pragma: no cover - defensive rendering path
            empty = ExplorerObjectsResponse(bucket=selected_bucket, prefix=prefix, next_cursor=None, entries=[])
            return HTMLResponse(_render_explorer(selected_bucket, prefix, buckets, empty, error=str(exc)))

    @router.post("/explorer/login")
    async def explorer_login(request: Request) -> Response:
        _assert_local_request(request)
        form = parse_qs((await request.body()).decode("utf-8"))
        token = form.get("token", [""])[0]
        if token != app.state.token:
            return HTMLResponse(_render_login(error="Invalid token"), status_code=401)
        sid = _create_session()
        resp = RedirectResponse(url="/explorer", status_code=303)
        resp.set_cookie(
            key=app.state.explorer_cookie_name,
            value=sid,
            httponly=True,
            samesite="lax",
            max_age=app.state.explorer_session_ttl,
        )
        return resp

    @router.post("/explorer/logout")
    def explorer_logout(request: Request) -> Response:
        _assert_local_request(request)
        sid = request.cookies.get(app.state.explorer_cookie_name)
        if sid:
            app.state.explorer_sessions.pop(sid, None)
        resp = RedirectResponse(url="/explorer", status_code=303)
        resp.delete_cookie(app.state.explorer_cookie_name)
        return resp

    @router.get("/explorer/health")
    def explorer_health(request: Request) -> dict[str, str]:
        _assert_local_request(request)
        return {"status": "ok"}

    return router
