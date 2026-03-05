from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "prefect_flush_completed.py"
    spec = importlib.util.spec_from_file_location("prefect_flush_completed", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_cursor_seen_and_advance(tmp_path: Path) -> None:
    mod = _load_module()
    cursor_path = tmp_path / "cursor.json"

    cursor = mod.Cursor.load(cursor_path)
    assert cursor.last_end_time == ""
    assert not cursor.seen("r1", "2026-03-05T00:00:00Z")

    cursor.advance("r1", "2026-03-05T00:00:00Z")
    cursor.save(cursor_path)

    loaded = mod.Cursor.load(cursor_path)
    assert loaded.seen("r1", "2026-03-05T00:00:00Z")
    assert not loaded.seen("r2", "2026-03-05T00:00:00Z")

    loaded.advance("r2", "2026-03-05T00:00:00Z")
    assert loaded.seen("r2", "2026-03-05T00:00:00Z")
    assert loaded.seen("r0", "2026-03-04T00:00:00Z")


def test_main_dry_run_collects_without_upload(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    mod = _load_module()
    cursor_path = tmp_path / "cursor.json"

    monkeypatch.setenv("PREFECT_API_URL", "http://prefect.local/api")
    monkeypatch.setenv("FLUSH_TARGET_URL", "https://discoverex.qzz.io")
    monkeypatch.setenv("FLUSH_GATEWAY_TOKEN", "token")
    monkeypatch.setenv("FLUSH_CURSOR_PATH", str(cursor_path))

    runs = [
        {"id": "run-1", "end_time": "2026-03-05T00:00:00Z", "run_count": 1},
        {"id": "run-2", "end_time": "2026-03-05T00:01:00Z", "run_count": 1},
    ]
    monkeypatch.setattr(mod, "_list_completed_runs", lambda after_end_time, page_size, max_runs: runs)
    monkeypatch.setattr(mod, "_fetch_run_snapshot", lambda run_id: {"id": run_id})

    uploads: list[tuple[dict, dict]] = []

    def _fake_upload(run: dict, snapshot: dict) -> str:
        uploads.append((run, snapshot))
        return f"s3://bucket/{run['id']}.json"

    monkeypatch.setattr(mod, "_upload_snapshot", _fake_upload)
    monkeypatch.setattr(
        "sys.argv",
        ["prefect_flush_completed.py", "--once", "--dry-run", "--cursor-path", str(cursor_path)],
    )

    rc = mod.main()
    assert rc == 0
    assert uploads == []
    assert not cursor_path.exists()
