from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_shell_python_helpers() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "e2e"
        / "shell_python_helpers.py"
    )
    spec = importlib.util.spec_from_file_location("shell_python_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
