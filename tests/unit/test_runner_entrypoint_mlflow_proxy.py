from __future__ import annotations

import http.server
import json
import subprocess
import textwrap
import threading
from pathlib import Path
from socketserver import ThreadingMixIn

import pytest

from runner.adapters.outbound.git.runner import cleanup_workdir, run_entrypoint


class _ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(["git", *cmd], cwd=cwd, check=True, capture_output=True, text=True)


def _create_proxy_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "source"
    (repo / "src" / "proxy_repo").mkdir(parents=True)
    (repo / "src" / "proxy_repo" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "proxy-repo"',
                'version = "0.1.0"',
                'requires-python = ">=3.11"',
            ]
        ),
        encoding="utf-8",
    )
    (repo / "src" / "proxy_repo" / "flow.py").write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            import json
            import os
            from urllib import request

            from prefect import flow


            @flow
            def mlflow_probe_flow() -> dict[str, object]:
                uri = os.environ.get("MLFLOW_TRACKING_URI", "")
                remote = os.environ.get("ORCH_REMOTE_MLFLOW_TRACKING_URI", "")
                cf_id = os.environ.get("CF_ACCESS_CLIENT_ID", "")
                cf_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET", "")
                body = request.urlopen(
                    uri + "/api/2.0/mlflow/experiments/list", timeout=30
                ).read().decode("utf-8")
                print(
                    json.dumps(
                        {
                            "uri": uri,
                            "remote": remote,
                            "cf_id": cf_id,
                            "cf_secret": cf_secret,
                            "body": body,
                        },
                        ensure_ascii=True,
                    )
                )
                return {"uri": uri, "remote": remote}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    _git(["init"], cwd=repo)
    _git(["config", "user.name", "Test User"], cwd=repo)
    _git(["config", "user.email", "test@example.com"], cwd=repo)
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)
    _git(["branch", "-M", "main"], cwd=repo)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repo, commit


def test_run_entrypoint_proxies_remote_mlflow_with_cf_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            seen["cf_id"] = self.headers.get("CF-Access-Client-Id", "")
            seen["cf_secret"] = self.headers.get("CF-Access-Client-Secret", "")
            payload = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = _ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    repo, commit = _create_proxy_repo(tmp_path)
    runtime_root = tmp_path / "runtime"
    upstream = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setenv("ORCH_WORKER_RUNTIME_DIR", str(runtime_root))
    artifacts = run_entrypoint(
        repo_url=str(repo),
        ref="main",
        resolved_commit=commit,
        flow_entrypoint="src/proxy_repo/flow.py:mlflow_probe_flow",
        run_mode="repo",
        env={
            "MLFLOW_TRACKING_URI": upstream,
            "CF_ACCESS_CLIENT_ID": "worker-id",
            "CF_ACCESS_CLIENT_SECRET": "worker-secret",
        },
        engine="discoverex",
        config_rel_path=None,
        inputs={},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-mlflow-proxy",
    )
    try:
        payload = json.loads(artifacts.stdout_path.read_text(encoding="utf-8").strip())
        assert artifacts.exit_code == 0
        assert payload["uri"].startswith("http://127.0.0.1:")
        assert payload["uri"] != upstream
        assert payload["remote"] == upstream
        assert payload["cf_id"] == ""
        assert payload["cf_secret"] == ""
        assert payload["body"] == '{"ok": true}'
        assert seen == {"cf_id": "worker-id", "cf_secret": "worker-secret"}
    finally:
        cleanup_workdir(artifacts.workdir)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
