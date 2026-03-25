from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

from minio import Minio


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    endpoint = os.getenv("MINIO_ENDPOINT", "127.0.0.1:19000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    secure = _env_bool("MINIO_SECURE", False)

    backup_root = Path(os.getenv("BACKUP_ROOT", "./backups/minio"))
    sample_limit = int(os.getenv("RESTORE_DRILL_SAMPLE", "3"))

    runs = sorted([p for p in backup_root.iterdir() if p.is_dir()])
    if not runs:
        raise SystemExit(f"no backup runs in {backup_root}")

    latest = runs[-1]
    client = Minio(
        endpoint, access_key=access_key, secret_key=secret_key, secure=secure
    )
    drill_bucket = f"restore-drill-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    client.make_bucket(drill_bucket)

    restored = 0
    checked = 0
    for bucket_dir in [p for p in latest.iterdir() if p.is_dir()]:
        for file_path in bucket_dir.rglob("*"):
            if not file_path.is_file():
                continue
            object_key = str(file_path.relative_to(bucket_dir))
            client.fput_object(drill_bucket, object_key, str(file_path))
            restored += 1
            if checked < sample_limit:
                download_path = latest / f".drill-{checked}.bin"
                client.fget_object(drill_bucket, object_key, str(download_path))
                if _sha256(file_path) != _sha256(download_path):
                    raise SystemExit(f"checksum mismatch for {object_key}")
                download_path.unlink(missing_ok=True)
                checked += 1

    print(
        f"restore_drill_complete source={latest} drill_bucket={drill_bucket} "
        f"restored_objects={restored} checked={checked}"
    )


if __name__ == "__main__":
    main()
