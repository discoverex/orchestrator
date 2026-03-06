from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "prefect_prune_completed.py"
    spec = importlib.util.spec_from_file_location("prefect_prune_completed", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_list_targets_uses_completed_and_cutoff(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()

    calls: list[dict[str, object]] = []

    def _fake_json_request(
        method: str, path: str, payload: dict[str, object] | None = None
    ) -> list[dict[str, str]]:
        assert method == "POST"
        assert path == "flow_runs/filter"
        assert payload is not None
        calls.append(payload)
        if payload["offset"] == 0:
            return [{"id": "r1"}]
        return []

    monkeypatch.setattr(mod, "_json_request", _fake_json_request)
    rows = mod._list_targets("2026-03-01T00:00:00Z", page_size=100, max_runs=500)
    assert rows == [{"id": "r1"}]
    first = calls[0]
    flow_runs = first.get("flow_runs")
    assert isinstance(flow_runs, dict)
    state = flow_runs.get("state")
    assert isinstance(state, dict)
    state_type = state.get("type")
    assert isinstance(state_type, dict)
    assert state_type.get("any_") == ["COMPLETED"]
    end_time = flow_runs.get("end_time")
    assert isinstance(end_time, dict)
    assert end_time.get("before_") == "2026-03-01T00:00:00Z"


def test_main_apply_deletes_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    monkeypatch.setenv("PREFECT_API_URL", "http://prefect.local/api")
    monkeypatch.setenv("PRUNE_TTL_HOURS", "72")

    monkeypatch.setattr(mod, "_list_targets", lambda cutoff_iso, page_size, max_runs: [{"id": "run-a"}, {"id": "run-b"}])
    deleted: list[str] = []
    monkeypatch.setattr(mod, "_delete_run", lambda run_id: deleted.append(run_id))
    monkeypatch.setattr("sys.argv", ["prefect_prune_completed.py", "--apply"])

    rc = mod.main()
    assert rc == 0
    assert deleted == ["run-a", "run-b"]
