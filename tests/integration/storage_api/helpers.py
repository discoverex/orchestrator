from __future__ import annotations

import importlib
from datetime import datetime, timezone
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from storage.application.models import ExplorerHeadResult, PresignResult
from storage.domain.models.object_ref import ObjectListEntry, ObjectStat
from worker_router.app import create_app

worker_router_app_module = importlib.import_module("worker_router.app")


class DummyStorageApp:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.bucket = "orchestrator-artifacts"

    def _object_uri(self, flow_run_id: str, attempt: int, filename: str) -> str:
        return f"s3://{self.bucket}/jobs/{flow_run_id}/attempt-{attempt}/{filename}"

    def issue_presign(
        self,
        *,
        flow_run_id: str,
        attempt: int,
        filename: str,
        method: str,
        ttl_seconds: int | None,
    ) -> PresignResult:
        ttl = 900 if ttl_seconds is None else ttl_seconds
        if ttl > 3600:
            raise ValueError("ttl_seconds must be <= 3600")
        object_uri = self._object_uri(flow_run_id, attempt, filename)
        return PresignResult(
            object_uri=object_uri,
            url=f"https://object.example/{filename}?method={method}&ttl={ttl}",
            expires_at=datetime.now(timezone.utc),
        )

    def issue_batch_put(self, *, entries: list[Any]) -> list[PresignResult]:
        return [
            self.issue_presign(
                flow_run_id=e.flow_run_id,
                attempt=e.attempt,
                filename=e.filename,
                method="PUT",
                ttl_seconds=e.ttl_seconds,
            )
            for e in entries
        ]

    def head_object(self, object_uri: str) -> ExplorerHeadResult:
        if object_uri not in self.objects:
            return ExplorerHeadResult(exists=False, stat=None)
        return ExplorerHeadResult(
            exists=True,
            stat=ObjectStat(uri=object_uri, size=len(self.objects[object_uri])),
        )

    def list_buckets(self) -> list[str]:
        return [self.bucket]

    def list_objects(
        self,
        *,
        bucket: str,
        prefix: str = "",
        cursor: str | None = None,
        limit: int = 200,
    ) -> tuple[list[ObjectListEntry], str | None]:
        _ = bucket
        rows: list[ObjectListEntry] = []
        for object_uri, data in sorted(self.objects.items()):
            key = object_uri.split("/", 3)[-1]
            if not key.startswith(prefix):
                continue
            if cursor and key <= cursor:
                continue
            rows.append(
                ObjectListEntry(
                    object_uri=object_uri,
                    object_key=key,
                    size=len(data),
                    last_modified=None,
                )
            )
            if len(rows) >= limit:
                break
        next_cursor = rows[-1].object_key if len(rows) >= limit else None
        return rows, next_cursor

    def download_object(self, object_uri: str) -> bytes:
        return self.objects[object_uri]


def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    storage_app = DummyStorageApp()
    monkeypatch.setattr(
        worker_router_app_module, "build_storage_app_from_env", lambda: storage_app
    )
    monkeypatch.setenv("GATEWAY_REQUIRE_CF_ACCESS", "false")
    test_client = TestClient(create_app())
    cast(FastAPI, test_client.app).state.storage_app = storage_app
    return test_client


def cf_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    storage_app = DummyStorageApp()
    monkeypatch.setattr(
        worker_router_app_module, "build_storage_app_from_env", lambda: storage_app
    )
    monkeypatch.setenv("GATEWAY_REQUIRE_CF_ACCESS", "true")
    monkeypatch.setenv("STORAGE_API_HOST", "storage-api.discoverex.qzz.io")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")
    test_client = TestClient(create_app())
    cast(FastAPI, test_client.app).state.storage_app = storage_app
    return test_client
