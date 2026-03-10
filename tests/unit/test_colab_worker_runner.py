from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

COLAB_DIR = (
    Path(__file__).resolve().parents[2]
    / "infra"
    / "stacks"
    / "worker"
    / "colab"
)


def _load_module(name: str) -> ModuleType:
    if str(COLAB_DIR) not in sys.path:
        sys.path.insert(0, str(COLAB_DIR))
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def _build_config(runtime_mod: ModuleType, tmp_path: Path) -> object:
    return runtime_mod.ColabRuntimeConfig(
        repo_dir=tmp_path / "repo",
        cache_root=tmp_path / "cache",
        venv_dir=tmp_path / "venv",
        checkpoint_dir=tmp_path / "checkpoints",
        pid_file=tmp_path / "worker.pid",
        log_file=tmp_path / "worker.log",
        python_bin="python3",
    )


def test_prefect_env_sets_default_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _load_module("colab_runtime")
    monkeypatch.delenv("PREFECT_WORK_QUEUE", raising=False)
    monkeypatch.delenv("PREFECT_CLIENT_CUSTOM_HEADERS", raising=False)
    monkeypatch.delenv("PREFECT_CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("PREFECT_CF_ACCESS_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)

    env = runtime.prefect_env()

    assert env["PREFECT_WORK_QUEUE"] == "gpu-colab"
    assert "PREFECT_CLIENT_CUSTOM_HEADERS" not in env


def test_populate_colab_env_maps_generic_cf_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _load_module("colab_runtime")
    config = _build_config(runtime, tmp_path)
    monkeypatch.delenv("PREFECT_CLIENT_CUSTOM_HEADERS", raising=False)
    monkeypatch.delenv("PREFECT_CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("PREFECT_CF_ACCESS_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "generic-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "generic-secret")

    snapshot = runtime.populate_colab_env(config)

    assert snapshot["prefect_work_queue"] == "gpu-colab"
    assert runtime.clean_env_value(os.environ["CF_ACCESS_CLIENT_ID"]) == "generic-id"
    assert "CF-Access-Client-Id" in os.environ["PREFECT_CLIENT_CUSTOM_HEADERS"]


def test_load_dotenv_sets_missing_values_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _load_module("colab_runtime")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PREFECT_API_URL=https://prefect.example/api\nPREFECT_WORK_POOL=gpu-pool\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("PREFECT_API_URL", raising=False)
    monkeypatch.setenv("PREFECT_WORK_POOL", "existing-pool")

    runtime.load_dotenv(env_path)

    assert os.environ["PREFECT_API_URL"] == "https://prefect.example/api"
    assert os.environ["PREFECT_WORK_POOL"] == "existing-pool"


def test_resolve_path_uses_repo_root_for_relative_paths() -> None:
    runtime = _load_module("colab_runtime")

    resolved = runtime.resolve_path(Path("infra/stacks/worker/colab"))

    assert resolved == runtime.REPO_ROOT / "infra/stacks/worker/colab"


def test_bootstrap_env_sets_pip_and_xdg_cache(tmp_path: Path) -> None:
    bootstrap = _load_module("colab_bootstrap")

    env = bootstrap.bootstrap_env(tmp_path / "cache")

    assert env["PIP_CACHE_DIR"].endswith("/cache/pip")
    assert env["XDG_CACHE_HOME"].endswith("/cache/xdg")


def test_prepare_cache_dirs_creates_pip_and_xdg_only(tmp_path: Path) -> None:
    bootstrap = _load_module("colab_bootstrap")
    cache_root = tmp_path / "cache"

    bootstrap.prepare_cache_dirs(cache_root)

    assert (cache_root / "pip").is_dir()
    assert (cache_root / "xdg").is_dir()
    assert sorted(path.name for path in cache_root.iterdir()) == ["pip", "xdg"]


def test_recreate_venv_removes_existing_dir_before_creation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _load_module("colab_runtime")
    bootstrap = _load_module("colab_bootstrap")
    config = _build_config(runtime, tmp_path)
    config.venv_dir.mkdir(parents=True)
    calls: list[tuple[str, object]] = []

    def fake_rmtree(path: Path) -> None:
        calls.append(("rmtree", path))

    def fake_run_command(**kwargs: object) -> object:
        raise AssertionError("unexpected kwargs-only call")

    def fake_run(
        cmd: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
        check: bool = True,
        step: str,
    ) -> object:
        del env, cwd, check, step
        calls.append(("run", cmd))
        bin_dir = config.venv_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "python").write_text("", encoding="utf-8")
        return SimpleNamespace(output="")

    monkeypatch.setattr(bootstrap.shutil, "rmtree", fake_rmtree)
    monkeypatch.setattr(bootstrap, "run_command", fake_run)

    python_path = bootstrap.recreate_venv(config, {})

    assert calls == [
        ("rmtree", config.venv_dir),
        ("run", ["python3", "-m", "venv", str(config.venv_dir)]),
    ]
    assert python_path == config.venv_dir / "bin" / "python"


def test_bootstrap_runtime_uses_editable_no_build_isolation_and_fast_deps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime = _load_module("colab_runtime")
    bootstrap = _load_module("colab_bootstrap")
    config = _build_config(runtime, tmp_path)
    config.repo_dir.mkdir()
    commands: list[list[str]] = []

    def fake_recreate(target_config: object, env: dict[str, str]) -> Path:
        assert target_config == config
        assert env["PIP_CACHE_DIR"] == str(config.cache_root / "pip")
        return config.venv_python

    def fake_run(
        cmd: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
        check: bool = True,
        step: str,
    ) -> object:
        del env, cwd, check, step
        commands.append(cmd)
        return SimpleNamespace(output="ok")

    monkeypatch.setattr(bootstrap, "ensure_drive_mounted", lambda: None)
    monkeypatch.setattr(bootstrap, "recreate_venv", fake_recreate)
    monkeypatch.setattr(bootstrap, "run_command", fake_run)

    bootstrap.bootstrap_runtime(config)

    assert commands == [
        [
            str(config.venv_python),
            "-m",
            "pip",
            "install",
            "-U",
            "pip",
            "setuptools",
            "wheel",
        ],
        [
            str(config.venv_python),
            "-m",
            "pip",
            "install",
            "-e",
            str(config.repo_dir),
            "--no-build-isolation",
            "--use-feature=fast-deps",
        ],
        [str(config.venv_python), "-m", "pip", "show", "orchestrator"],
        [str(config.venv_python), "--version"],
    ]
    output = capsys.readouterr().out
    assert f"ready repo={config.repo_dir}" in output
    assert f"ready cache={config.cache_root}" in output
    assert f"ready venv={config.venv_dir}" in output


def test_ensure_drive_mounted_requires_drive(monkeypatch: pytest.MonkeyPatch) -> None:
    bootstrap = _load_module("colab_bootstrap")
    monkeypatch.setattr(bootstrap.Path, "exists", lambda self: False)

    with pytest.raises(RuntimeError, match="Google Drive is not mounted"):
        bootstrap.ensure_drive_mounted()


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
            venv_dir="/tmp/venv",
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
