from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_bin_cli_help() -> None:
    proc = subprocess.run(
        ["bash", "bin/cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "cli <domain> <action>" in proc.stdout
    assert "prefect" in proc.stdout


def test_bin_cli_runtime_init_routes(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["RUNTIME_ROOT"] = str(tmp_path / "runtime")

    proc = subprocess.run(
        ["bash", "bin/cli", "runtime", "init", "all"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0
    assert (tmp_path / "runtime" / "storage" / "data" / "minio").is_dir()
    assert (tmp_path / "runtime" / "worker" / "checkpoints").is_dir()


def test_legacy_cli_entrypoints_removed() -> None:
    assert not Path("bin/project").exists()
    assert not Path("bin/remote").exists()


def test_docs_use_bin_cli() -> None:
    targets = [
        Path("README.md"),
        Path("docs/guides/setup-prefect.md"),
        Path("docs/guides/setup-storage.md"),
        Path("infra/stacks/prefect-server/README.md"),
        Path("infra/stacks/worker/fixed/README.md"),
    ]

    for path in targets:
        content = path.read_text(encoding="utf-8")
        assert "bin/project" not in content
        assert "bin/remote" not in content
        assert "bin/cli" in content
