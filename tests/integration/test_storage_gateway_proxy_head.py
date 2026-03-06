from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from storage_gateway.main import app
from tests.integration.storage_gateway.helpers import client


def test_head_endpoint() -> None:
    c = client()
    app.state.storage_app.objects["s3://bucket/x/exists.log"] = b"hello-world!!"
    yes = c.post(
        "/v1/object/head",
        headers={"Authorization": "Bearer test-token"},
        json={"object_uri": "s3://bucket/x/exists.log"},
    )
    no = c.post(
        "/v1/object/head",
        headers={"Authorization": "Bearer test-token"},
        json={"object_uri": "s3://bucket/x/missing.log"},
    )
    assert yes.status_code == 200
    assert yes.json() == {"exists": True, "size": 13}
    assert no.status_code == 200
    assert no.json() == {"exists": False, "size": None}


def test_proxy_put_and_get_roundtrip() -> None:
    c = client()
    put_res = c.post(
        "/v1/presign/put",
        headers={"Authorization": "Bearer test-token"},
        json={
            "flow_run_id": "f3",
            "attempt": 1,
            "kind": "result",
            "filename": "payload.bin",
        },
    )
    assert put_res.status_code == 200
    put_url = put_res.json()["url"]
    put_token = parse_qs(urlparse(put_url).query)["token"][0]

    uploaded = c.put(
        f"/v1/object/proxy?token={put_token}",
        content=b"payload-data",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert uploaded.status_code == 200

    get_res = c.post(
        "/v1/presign/get",
        headers={"Authorization": "Bearer test-token"},
        json={
            "flow_run_id": "f3",
            "attempt": 1,
            "kind": "result",
            "filename": "payload.bin",
        },
    )
    assert get_res.status_code == 200
    get_token = parse_qs(urlparse(get_res.json()["url"]).query)["token"][0]

    downloaded = c.get(f"/v1/object/proxy?token={get_token}")
    assert downloaded.status_code == 200
    assert downloaded.content == b"payload-data"
