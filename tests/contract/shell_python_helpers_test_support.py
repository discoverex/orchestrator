from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_module() -> ModuleType:
    script_dir = Path(__file__).resolve().parents[2] / "scripts" / "e2e"
    path = script_dir / "shell_python_helpers.py"
    spec = importlib.util.spec_from_file_location("shell_python_helpers", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod
