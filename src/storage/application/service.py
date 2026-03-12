from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..ports.object_store import ObjectStorePort
from .models import ExplorerHeadResult, ExplorerListResult, PresignResult


@dataclass(frozen=True)
class PresignEntry:
    flow_run_id: str
    attempt: int
    kind: str
    filename: str
    ttl_seconds: int | None = None


class StorageApplicationService:
    def __init__(
        self,
        object_store: ObjectStorePort,
        bucket: str,
        ttl_default: int = 900,
        ttl_max: int = 3600,
    ) -> None:
        self.object_store = object_store
        self.bucket = bucket
        self.ttl_default = ttl_default
        self.ttl_max = ttl_max

    def validate_ttl(self, ttl_seconds: int | None) -> int:
        value = ttl_seconds if ttl_seconds is not None else self.ttl_default
        if value <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if value > self.ttl_max:
            raise ValueError(f"ttl_seconds must be <= {self.ttl_max}")
        return value

    def build_object_uri(self, flow_run_id: str, attempt: int, filename: str) -> str:
        clean = filename.lstrip("/")
        return f"s3://{self.bucket}/jobs/{flow_run_id}/attempt-{attempt}/{clean}"

    def issue_presign(
        self,
        *,
        flow_run_id: str,
        attempt: int,
        filename: str,
        method: str,
        ttl_seconds: int | None,
    ) -> PresignResult:
        ttl = self.validate_ttl(ttl_seconds)
        object_uri = self.build_object_uri(
            flow_run_id=flow_run_id, attempt=attempt, filename=filename
        )
        if method == "PUT":
            url = self.object_store.generate_presigned_put(object_uri, ttl)
        else:
            url = self.object_store.generate_presigned_get(object_uri, ttl)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
        return PresignResult(object_uri=object_uri, url=url, expires_at=expires_at)

    def issue_batch_put(self, *, entries: list[PresignEntry]) -> list[PresignResult]:
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
        stat = self.object_store.stat(object_uri)
        return ExplorerHeadResult(exists=stat is not None, stat=stat)

    def list_buckets(self) -> list[str]:
        return self.object_store.list_buckets()

    def list_objects(
        self,
        *,
        bucket: str,
        prefix: str = "",
        cursor: str | None = None,
        limit: int = 200,
    ) -> ExplorerListResult:
        entries, next_cursor = self.object_store.list_objects(
            bucket=bucket,
            prefix=prefix,
            start_after=cursor,
            limit=limit,
        )
        return ExplorerListResult(
            bucket=bucket, prefix=prefix, next_cursor=next_cursor, entries=entries
        )

    def download_object(self, object_uri: str) -> bytes:
        return self.object_store.download_bytes(object_uri)
