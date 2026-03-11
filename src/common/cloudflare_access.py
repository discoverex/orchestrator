from __future__ import annotations

from fastapi import HTTPException


def normalize_host(host: str | None) -> str:
    value = (host or "").strip().lower()
    if ":" in value:
        value = value.split(":", 1)[0]
    return value


def require_service_token(
    *,
    enabled: bool,
    expected_id: str,
    expected_secret: str,
    provided_id: str | None,
    provided_secret: str | None,
) -> None:
    if not enabled:
        return
    if not expected_id or not expected_secret:
        raise HTTPException(status_code=500, detail="cf_access_not_configured")
    if provided_id != expected_id or provided_secret != expected_secret:
        raise HTTPException(status_code=403, detail="cf_access_forbidden")
