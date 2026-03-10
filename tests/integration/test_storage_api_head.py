from __future__ import annotations

from typing import cast

import pytest
from fastapi import FastAPI

from tests.integration.storage_api.helpers import client


def test_head_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch)
    cast(FastAPI, c.app).state.storage_app.objects["s3://bucket/x/exists.log"] = (
        b"hello-world!!"
    )

    yes = c.post(
        "/artifact/v1/object/head",
        json={"object_uri": "s3://bucket/x/exists.log"},
    )
    no = c.post(
        "/artifact/v1/object/head",
        json={"object_uri": "s3://bucket/x/missing.log"},
    )

    assert yes.status_code == 200
    assert yes.json() == {"exists": True, "size": 13}
    assert no.status_code == 200
    assert no.json() == {"exists": False, "size": None}


def test_storage_compatibility_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch)

    res = c.post(
        "/storage/artifact/v1/presign/get",
        json={
            "flow_run_id": "f3",
            "attempt": 1,
            "kind": "result",
            "filename": "payload.bin",
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert (
        payload["object_uri"]
        == "s3://orchestrator-artifacts/jobs/f3/attempt-1/payload.bin"
    )
    assert payload["url"].startswith("https://object.example/payload.bin")
