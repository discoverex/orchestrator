from __future__ import annotations

from datetime import datetime, timedelta, timezone

from common import StrictModel

from ..domain.models.object_ref import ObjectStat
from ..ports.object_store import ObjectStorePort
from ..ports.token_signer import TokenSignerPort
from .models import ExplorerHeadResult, ExplorerListResult, PresignResult


class PresignEntry(StrictModel):
    flow_run_id: str
    attempt: int
    kind: str
    filename: str
    ttl_seconds: int | None = None


class StorageApplicationService:
    def __init__(
        self,
        object_store: ObjectStorePort,
        token_signer: TokenSignerPort,
        bucket: str,
        ttl_default: int = 900,
        ttl_max: int = 3600,
        presign_mode: str = "gateway",
        public_base_url: str = "",
    ) -> None:
        self.object_store = object_store
        self.token_signer = token_signer
        self.bucket = bucket
        self.ttl_default = ttl_default
        self.ttl_max = ttl_max
        self.presign_mode = presign_mode
        self.public_base_url = public_base_url

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

    def _gateway_url(
        self, base_url: str, method: str, object_uri: str, ttl_seconds: int
    ) -> str:
        base = (self.public_base_url or base_url).rstrip("/")
        token = self.token_signer.mint(
            method=method, object_uri=object_uri, ttl_seconds=ttl_seconds
        )
        return f"{base}/v1/object/proxy?token={token}"

    def issue_presign(
        self,
        *,
        flow_run_id: str,
        attempt: int,
        filename: str,
        method: str,
        base_url: str,
        ttl_seconds: int | None,
    ) -> PresignResult:
        ttl = self.validate_ttl(ttl_seconds)
        object_uri = self.build_object_uri(
            flow_run_id=flow_run_id, attempt=attempt, filename=filename
        )
        if self.presign_mode == "gateway":
            url = self._gateway_url(
                base_url=base_url, method=method, object_uri=object_uri, ttl_seconds=ttl
            )
        elif method == "PUT":
            url = self.object_store.generate_presigned_put(object_uri, ttl)
        else:
            url = self.object_store.generate_presigned_get(object_uri, ttl)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        return PresignResult(object_uri=object_uri, url=url, expires_at=expires_at)

    def issue_batch_put(
        self, *, entries: list[PresignEntry], base_url: str
    ) -> list[PresignResult]:
        return [
            self.issue_presign(
                flow_run_id=e.flow_run_id,
                attempt=e.attempt,
                filename=e.filename,
                method="PUT",
                base_url=base_url,
                ttl_seconds=e.ttl_seconds,
            )
            for e in entries
        ]

    def proxy_upload(self, *, token: str, data: bytes, content_type: str) -> ObjectStat:
        object_uri = self.token_signer.decode(token=token, expected_method="PUT")
        return self.object_store.upload_bytes(
            data, object_uri, content_type=content_type
        )

    def proxy_download(self, *, token: str) -> bytes:
        object_uri = self.token_signer.decode(token=token, expected_method="GET")
        return self.object_store.download_bytes(object_uri)

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
