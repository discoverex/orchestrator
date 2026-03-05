from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


SCRIPT = Path("infra/stacks/prefect-server/deploy.sh")


def _write_fake_docker(bin_dir: Path, log_path: Path) -> None:
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "echo \"$*\" >> \"" + str(log_path) + "\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)


def _base_env(deploy_dir: Path, bin_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env.update(
        {
            "REMOTE_DEPLOY_PATH": str(deploy_dir),
            "PREFECT_SERVER_IMAGE": "ghcr.io/org/orchestrator/prefect-server:sha-test",
            "PREFECT_API_PUBLIC_URL": "https://prefect.example.com/api",
            "PREFECT_DB_PASSWORD": "pw",
            "FLUSH_TARGET_URL": "https://storage.example.com",
            "FLUSH_GATEWAY_TOKEN": "token",
        }
    )
    return env


def test_deploy_script_fails_when_required_env_missing(tmp_path: Path) -> None:
    deploy_dir = tmp_path / "deploy"
    deploy_dir.mkdir()
    (deploy_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_docker(bin_dir, tmp_path / "docker.log")

    env = _base_env(deploy_dir, bin_dir)
    env.pop("FLUSH_GATEWAY_TOKEN", None)

    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "missing required env: FLUSH_GATEWAY_TOKEN" in proc.stderr


def test_deploy_script_applies_defaults_and_runs_compose(tmp_path: Path) -> None:
    deploy_dir = tmp_path / "deploy"
    deploy_dir.mkdir()
    (deploy_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "docker.log"
    _write_fake_docker(bin_dir, log_path)

    env = _base_env(deploy_dir, bin_dir)
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert any(line.startswith("compose pull") for line in lines)
    assert any("compose up -d prefect-db prefect-server prefect-maintenance" in line for line in lines)
    assert any(line.startswith("compose ps") for line in lines)
