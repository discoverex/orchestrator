from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

COLAB_DIR = (
    Path(__file__).resolve().parents[2] / "infra" / "stacks" / "worker" / "colab"
)


def _load_module(name: str) -> ModuleType:
    if str(COLAB_DIR) not in sys.path:
        sys.path.insert(0, str(COLAB_DIR))
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_start_requires_bootstrap_when_prefect_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _load_module("colab_worker")

    def missing_version(_: str) -> str:
        raise worker.importlib.metadata.PackageNotFoundError()

    monkeypatch.setattr(worker.importlib.metadata, "version", missing_version)

    with pytest.raises(RuntimeError, match="Run bootstrap first"):
        worker.ensure_runtime_ready(skip_install=False)


def test_start_allows_installed_prefect(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = _load_module("colab_worker")
    monkeypatch.setattr(worker.importlib.metadata, "version", lambda _: "3.1.0")

    worker.ensure_runtime_ready(skip_install=True)


def test_worker_status_handles_running_and_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worker = _load_module("colab_worker")
    pid_file = tmp_path / "worker.pid"
    pid_file.write_text("123", encoding="utf-8")

    monkeypatch.setattr(worker, "is_running", lambda pid: pid == 123)
    running = worker.worker_status(pid_file)
    assert running.running is True

    monkeypatch.setattr(worker, "is_running", lambda pid: False)
    stale = worker.worker_status(pid_file)
    assert stale.running is False
    assert stale.pid == 123


def test_read_worker_logs_returns_tail(tmp_path: Path) -> None:
    worker = _load_module("colab_worker")
    log_file = tmp_path / "worker.log"
    log_file.write_text("a\nb\nc\n", encoding="utf-8")

    lines = worker.read_worker_logs(log_file, 2)

    assert lines == ["b", "c"]


def test_append_worker_log_banner_writes_clear_markers(tmp_path: Path) -> None:
    worker = _load_module("colab_worker")
    log_file = tmp_path / "worker.log"

    worker.append_worker_log_banner(
        log_file,
        position="top",
        pid=111,
        work_pool="gpu-pool",
        work_queue="gpu-colab",
    )
    worker.append_worker_log_banner(log_file, position="bottom", pid=111)

    content = log_file.read_text(encoding="utf-8")
    assert "worker start |" in content
    assert "worker stop |" in content
    assert "pool=gpu-pool" in content
    assert "queue=gpu-colab" in content
    assert "=" * 72 in content
    assert "-" * 72 in content


def test_stop_worker_terminates_process_group(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worker = _load_module("colab_worker")
    pid_file = tmp_path / "worker.pid"
    log_file = tmp_path / "worker.log"
    pid_file.write_text("321", encoding="utf-8")
    calls: list[tuple[str, int, int]] = []

    monkeypatch.setattr(worker, "wait_for_exit", lambda pid, timeout_seconds=10.0: True)

    def fake_killpg(pid: int, sig: int) -> None:
        calls.append(("killpg", pid, sig))

    monkeypatch.setattr(worker.os, "killpg", fake_killpg)

    status = worker.stop_worker(pid_file, log_file)

    assert status.running is False
    assert calls == [("killpg", 321, worker.signal.SIGTERM)]
    assert pid_file.exists() is False
    assert "worker stop |" in log_file.read_text(encoding="utf-8")


def test_stop_worker_reports_timeout_when_process_survives(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worker = _load_module("colab_worker")
    pid_file = tmp_path / "worker.pid"
    log_file = tmp_path / "worker.log"
    pid_file.write_text("654", encoding="utf-8")
    calls: list[tuple[str, int, int]] = []

    monkeypatch.setattr(
        worker, "wait_for_exit", lambda pid, timeout_seconds=10.0: False
    )

    def fake_killpg(pid: int, sig: int) -> None:
        calls.append(("killpg", pid, sig))

    monkeypatch.setattr(worker.os, "killpg", fake_killpg)

    status = worker.stop_worker(pid_file, log_file)

    assert status.running is True
    assert "timed out" in status.message
    assert calls == [
        ("killpg", 654, worker.signal.SIGTERM),
        ("killpg", 654, worker.signal.SIGKILL),
    ]
    assert pid_file.exists() is True
    assert "stop timed out; process still running" in log_file.read_text(
        encoding="utf-8"
    )


def test_runner_main_dispatches_status(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_module("colab_worker_runner")
    monkeypatch.setattr(
        runner,
        "_parse_args",
        lambda: SimpleNamespace(
            command="status",
            pid_file="/tmp/test.pid",
            log_file="/tmp/test.log",
            tail=10,
            checkpoint_dir="/tmp/checkpoints",
            repo_dir="/tmp/repo",
            cache_root="/tmp/cache",
            python_bin="python3",
            skip_install=False,
        ),
    )
    monkeypatch.setattr(
        runner,
        "worker_status",
        lambda pid_file: SimpleNamespace(running=True, message=f"ok:{pid_file}"),
    )

    assert runner.main() == 0
