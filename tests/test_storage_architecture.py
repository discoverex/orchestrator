from __future__ import annotations

import ast
from pathlib import Path


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.append(node.module)
    return out


def _py_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_domain_has_no_framework_imports() -> None:
    root = Path("src/storage/domain")
    forbidden_prefixes = ("fastapi", "minio", "pydantic", "uvicorn")
    forbidden_exact = {"os", "http", "requests"}
    violations: list[str] = []
    for path in _py_files(root):
        for module in _imports(path):
            if module.startswith(forbidden_prefixes) or module in forbidden_exact:
                violations.append(f"{path}: {module}")
    assert not violations, "\n".join(violations)


def test_application_does_not_import_fastapi() -> None:
    root = Path("src/storage/application")
    violations: list[str] = []
    for path in _py_files(root):
        for module in _imports(path):
            if module.startswith("fastapi"):
                violations.append(f"{path}: {module}")
    assert not violations, "\n".join(violations)


def test_gateway_and_explorer_do_not_import_storage_adapters() -> None:
    roots = [Path("src/storage_gateway"), Path("src/storage_explorer")]
    violations: list[str] = []
    for root in roots:
        for path in _py_files(root):
            for module in _imports(path):
                if module.startswith("storage.adapters"):
                    violations.append(f"{path}: {module}")
    assert not violations, "\n".join(violations)
