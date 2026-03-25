from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from storage.application.models import ExplorerHeadResult, PresignResult
from storage.domain.models.object_ref import ObjectStat
from storage.interfaces.http import build_artifact_router


class DummyStorageService:
    def issue_presign(
        self,
        *,
        flow_run_id: str,
        attempt: int,
        filename: str,
        method: str,
        ttl_seconds: int | None,
    ) -> PresignResult:
        if ttl_seconds == 9999:
            raise ValueError("ttl_seconds must be <= 3600")
        return PresignResult(
            object_uri=f"s3://bucket/jobs/{flow_run_id}/attempt-{attempt}/{filename}",
            url=f"https://storage.example/{filename}?method={method}",
            expires_at=datetime.now(UTC),
        )

    def issue_batch_put(self, *, entries: list[Any]) -> list[PresignResult]:
        rows: list[PresignResult] = []
        for entry in entries:
            rows.append(
                self.issue_presign(
                    flow_run_id=entry.flow_run_id,
                    attempt=entry.attempt,
                    filename=entry.filename,
                    method="PUT",
                    ttl_seconds=entry.ttl_seconds,
                )
            )
        return rows

    def head_object(self, object_uri: str) -> ExplorerHeadResult:
        return ExplorerHeadResult(exists=True, stat=ObjectStat(uri=object_uri, size=13))


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(
        build_artifact_router(
            cast(Any, DummyStorageService()),
            lambda request, cf_id, cf_secret: None,
        )
    )
    return TestClient(app)


def test_router_maps_default_filename_for_manifest() -> None:
    res = _client().post(
        "/artifact/v1/presign/get",
        json={"flow_run_id": "f1", "attempt": 1, "kind": "manifest"},
    )

    assert res.status_code == 200
    assert res.json()["object_uri"].endswith("/artifacts.json")


def test_router_maps_value_error_to_400() -> None:
    res = _client().post(
        "/artifact/v1/presign/put",
        json={
            "flow_run_id": "f1",
            "attempt": 1,
            "kind": "stdout",
            "ttl_seconds": 9999,
        },
    )

    assert res.status_code == 400
    assert res.json()["detail"] == "ttl_seconds must be <= 3600"


def test_router_head_response_flattens_stat_size() -> None:
    res = _client().post(
        "/artifact/v1/object/head",
        json={"object_uri": "s3://bucket/jobs/f1/attempt-1/stdout.log"},
    )

    assert res.status_code == 200
    assert res.json() == {"exists": True, "size": 13}
