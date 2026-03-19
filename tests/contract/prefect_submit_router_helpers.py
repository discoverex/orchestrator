from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from typing import Any, cast

DEFAULT_PARAMETERS_JSON = (
    '{"run_mode":"repo","engine":"shell",'
    '"repo_url":"https://github.com/octocat/Hello-World.git",'
    '"ref":"master","entrypoint":["/bin/sh","-lc","echo test"],'
    '"config":null,"inputs":{},"env":{},"outputs_prefix":null}'
)


def load_router_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "ops"
        / "prefect_submit_router.py"
    )
    spec = importlib.util.spec_from_file_location("prefect_submit_router", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeParser:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def parse_args(self) -> object:
        return type("Args", (), self._payload)()


def fake_args(**overrides: object) -> FakeParser:
    payload: dict[str, object] = {
        "mode": "fixed-first",
        "strict_priority": "false",
        "queue_depth_threshold": 1,
        "divert_when_running": "true",
        "fixed_deployment": "e2e-job/e2e-test",
        "colab_deployment": "e2e-job/e2e-test-colab",
        "fixed_queue": "gpu-fixed",
        "colab_queue": "gpu-colab",
        "parameters_json": DEFAULT_PARAMETERS_JSON,
        "parameters_file": None,
        "resume_key": None,
        "checkpoint_dir": None,
        "parameter_overrides_json": None,
    }
    payload.update(overrides)
    return FakeParser(payload)


def capture_json_stdout(fn: Callable[[], int]) -> dict[str, Any]:
    import io

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn()
    assert rc == 0
    return cast(dict[str, Any], json.loads(buf.getvalue().strip()))
