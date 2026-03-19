from __future__ import annotations

import pytest

from tests.integration.storage_api.helpers import client


def test_upload_file_persists_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    test_client = client(monkeypatch)

    res = test_client.put(
        "/artifact/v1/upload/file",
        content=b"payload",
        headers={
            "X-Orch-Flow-Run-Id": "flow-1",
            "X-Orch-Attempt": "2",
            "X-Orch-Filename": "engine/output.txt",
            "Content-Type": "text/plain",
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert (
        payload["object_uri"]
        == "s3://orchestrator-artifacts/jobs/flow-1/attempt-2/engine/output.txt"
    )
    assert payload["size"] == 7
