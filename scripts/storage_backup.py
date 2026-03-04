from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from minio import Minio


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def main() -> None:
    endpoint = os.getenv("MINIO_ENDPOINT", "127.0.0.1:19000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    secure = _env_bool("MINIO_SECURE", False)

    backup_root = Path(os.getenv("BACKUP_ROOT", "./backups/minio"))
    retention_days = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))

    run_at = datetime.now(timezone.utc)
    stamp = run_at.strftime("%Y%m%dT%H%M%SZ")
    dest = backup_root / stamp
    dest.mkdir(parents=True, exist_ok=False)

    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    total_objects = 0
    total_bytes = 0
    buckets_manifest: list[dict[str, object]] = []

    for bucket in client.list_buckets():
        bucket_name = bucket.name
        bucket_dir = dest / bucket_name
        bucket_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        size_sum = 0
        for obj in client.list_objects(bucket_name, recursive=True):
            out_path = bucket_dir / obj.object_name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            client.fget_object(bucket_name, obj.object_name, str(out_path))
            count += 1
            size = int(obj.size or 0)
            size_sum += size
            total_objects += 1
            total_bytes += size

        buckets_manifest.append({"bucket": bucket_name, "objects": count, "bytes": size_sum})

    manifest = {
        "created_at": run_at.isoformat(),
        "endpoint": endpoint,
        "total_objects": total_objects,
        "total_bytes": total_bytes,
        "buckets": buckets_manifest,
    }
    (dest / "backup_manifest.json").write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")

    cutoff = run_at - timedelta(days=retention_days)
    for child in backup_root.iterdir():
        if not child.is_dir() or child.name == stamp:
            continue
        try:
            ts = datetime.strptime(child.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts < cutoff:
            for p in sorted(child.rglob("*"), reverse=True):
                if p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    p.rmdir()
            child.rmdir()

    print(f"backup_complete path={dest} objects={total_objects} bytes={total_bytes}")


if __name__ == "__main__":
    main()
