from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

from prefect.settings import (
    PREFECT_API_URL,
    PREFECT_CLIENT_CUSTOM_HEADERS,
    temporary_settings,
)


@contextlib.contextmanager
def patched_environ(values: dict[str, str]) -> Iterator[None]:
    original = os.environ.copy()
    os.environ.clear()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


@contextlib.contextmanager
def working_directory(path: Path) -> Iterator[None]:
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


@contextlib.contextmanager
def patched_sys_path(paths: list[Path]) -> Iterator[None]:
    original = list(sys.path)
    prefixes = [str(path) for path in paths if path.exists()]
    sys.path[:0] = prefixes
    try:
        yield
    finally:
        sys.path[:] = original


@contextlib.contextmanager
def child_prefect_settings() -> Iterator[None]:
    with temporary_settings(
        restore_defaults={
            PREFECT_API_URL,
            PREFECT_CLIENT_CUSTOM_HEADERS,
        }
    ):
        yield


def jsonable_result(value: object) -> object:
    try:
        json.dumps(value, ensure_ascii=True)
        return value
    except TypeError:
        return repr(value)


def prepare_child_prefect_env(env: dict[str, str], workdir: Path) -> dict[str, str]:
    sanitized = env.copy()
    for key in ("PREFECT_API_URL", "PREFECT_CLIENT_CUSTOM_HEADERS"):
        sanitized.pop(key, None)
    sanitized.setdefault("PREFECT_HOME", str(workdir / ".prefect"))
    return sanitized
