from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "prefect_submit_router.py"
    spec = importlib.util.spec_from_file_location("prefect_submit_router", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_router_diverts_when_fixed_running(monkeypatch) -> None:  # noqa: ANN001
    mod = _load_module()
    monkeypatch.setattr(
        mod,
        "_build_parser",
        lambda: _FakeParser(
            {
                "mode": "fixed-first",
                "strict_priority": "false",
                "queue_depth_threshold": 1,
                "divert_when_running": "true",
                "fixed_deployment": "engine-run",
                "colab_deployment": "engine-run-colab",
                "fixed_queue": "gpu-fixed",
                "colab_queue": "gpu-colab",
                "repo_url": "https://github.com/octocat/Hello-World.git",
                "ref": "master",
                "entrypoint": '["/bin/sh","-lc","echo test"]',
                "resume_key": None,
                "checkpoint_dir": None,
                "parameters_json": None,
            }
        ),
    )
    monkeypatch.setattr(mod, "_scheduled_count_for_queue", lambda q: 0)
    monkeypatch.setattr(mod, "_running_count_for_queue", lambda q: 1 if q == "gpu-fixed" else 0)
    monkeypatch.setattr(mod, "_find_deployment_id", lambda d: f"id-{d}")
    monkeypatch.setattr(mod, "_create_flow_run", lambda dep_id, params: {"id": "run-1", "name": "r1"})

    out = _capture_json_stdout(mod.main)
    assert out["selected_deployment"] == "engine-run-colab"
    assert out["reason"] == "running-diverted-to-secondary"


def test_router_strict_priority_keeps_preferred(monkeypatch) -> None:  # noqa: ANN001
    mod = _load_module()
    monkeypatch.setattr(
        mod,
        "_build_parser",
        lambda: _FakeParser(
            {
                "mode": "fixed-first",
                "strict_priority": "true",
                "queue_depth_threshold": 0,
                "divert_when_running": "true",
                "fixed_deployment": "engine-run",
                "colab_deployment": "engine-run-colab",
                "fixed_queue": "gpu-fixed",
                "colab_queue": "gpu-colab",
                "repo_url": "https://github.com/octocat/Hello-World.git",
                "ref": "master",
                "entrypoint": '["/bin/sh","-lc","echo test"]',
                "resume_key": None,
                "checkpoint_dir": None,
                "parameters_json": None,
            }
        ),
    )
    monkeypatch.setattr(mod, "_scheduled_count_for_queue", lambda q: 100 if q == "gpu-fixed" else 0)
    monkeypatch.setattr(mod, "_running_count_for_queue", lambda q: 100 if q == "gpu-fixed" else 0)
    monkeypatch.setattr(mod, "_find_deployment_id", lambda d: f"id-{d}")
    monkeypatch.setattr(mod, "_create_flow_run", lambda dep_id, params: {"id": "run-2", "name": "r2"})

    out = _capture_json_stdout(mod.main)
    assert out["selected_deployment"] == "engine-run"
    assert out["reason"] == "strict-priority-selected-preferred"


class _FakeParser:
    def __init__(self, payload):
        self._payload = payload

    def parse_args(self):
        return type("Args", (), self._payload)()


def _capture_json_stdout(fn):
    import io
    import json
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn()
    assert rc == 0
    return json.loads(buf.getvalue().strip())
