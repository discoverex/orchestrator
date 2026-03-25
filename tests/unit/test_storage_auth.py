from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI, HTTPException

from storage.interfaces.auth import authorize, authorize_dependency


def test_authorize_passes_when_service_token_matches() -> None:
    state = cast(
        Any,
        SimpleNamespace(
            require_cf_access=True,
            cf_client_id="cf-id",
            cf_client_secret="cf-secret",
        ),
    )

    authorize(state, "cf-id", "cf-secret")


def test_authorize_dependency_reads_headers() -> None:
    app = FastAPI()
    app.state.require_cf_access = True
    app.state.cf_client_id = "cf-id"
    app.state.cf_client_secret = "cf-secret"

    dependency = authorize_dependency(app)

    dependency("cf-id", "cf-secret")


def test_authorize_dependency_raises_for_wrong_header() -> None:
    app = FastAPI()
    app.state.require_cf_access = True
    app.state.cf_client_id = "cf-id"
    app.state.cf_client_secret = "cf-secret"

    dependency = authorize_dependency(app)

    with pytest.raises(HTTPException, match="cf_access_forbidden"):
        dependency("wrong", "cf-secret")
