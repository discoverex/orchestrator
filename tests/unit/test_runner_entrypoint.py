from __future__ import annotations

import http.server
import json
import sys
import threading
from socketserver import ThreadingMixIn

import pytest

from runner.git_runner import cleanup_workdir, run_entrypoint


class _ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def test_run_entrypoint_inline_mode_without_repo() -> None:
    artifacts = run_entrypoint(
        repo_url=None,
        ref=None,
        resolved_commit=None,
        entrypoint=["/bin/sh", "-lc", "echo inline-ok"],
        run_mode="inline",
        env={},
        engine="shell",
        config_rel_path=None,
        inputs={},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-smoke",
    )
    try:
        assert artifacts.exit_code == 0
        assert artifacts.stdout_path.read_text(encoding="utf-8").strip() == "inline-ok"
        result = artifacts.result_path.read_text(encoding="utf-8")
        assert '"run_mode": "inline"' in result
    finally:
        cleanup_workdir(artifacts.workdir)


def test_run_entrypoint_merges_job_and_orchestrator_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    artifacts = run_entrypoint(
        repo_url=None,
        ref=None,
        resolved_commit=None,
        entrypoint=[
            "/bin/sh",
            "-lc",
            (
                "printf '%s\\n' \"$ORCH_JOB_INPUTS_JSON\" > inputs.json && "
                "printf '%s\\n' \"$MLFLOW_TRACKING_URI\" && "
                "printf '%s\\n' \"$ORCH_ENGINE_ARTIFACT_DIR\" > artifact-dir.txt && "
                "printf '%s\\n' \"$ORCH_ENGINE_ARTIFACT_MANIFEST_PATH\" > artifact-manifest.txt"
            ),
        ],
        run_mode="inline",
        env={"MLFLOW_TRACKING_URI": "http://mlflow.example.com"},
        engine="discoverex",
        config_rel_path=None,
        inputs={"contract_version": "v2", "command": "generate"},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-env-check",
    )
    try:
        assert artifacts.exit_code == 0
        assert (
            artifacts.stdout_path.read_text(encoding="utf-8").strip()
            == "http://mlflow.example.com"
        )
        payload = artifacts.workdir / "inputs.json"
        assert '"contract_version": "v2"' in payload.read_text(encoding="utf-8")
        assert (
            artifacts.workdir / "artifact-dir.txt"
        ).read_text(encoding="utf-8").strip() == str(artifacts.engine_artifact_dir)
        assert (
            artifacts.workdir / "artifact-manifest.txt"
        ).read_text(encoding="utf-8").strip() == str(
            artifacts.engine_artifact_manifest_path
        )
    finally:
        cleanup_workdir(artifacts.workdir)


def test_run_entrypoint_proxies_remote_mlflow_with_cf_access() -> None:
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
    upstream = f"http://127.0.0.1:{server.server_address[1]}"
    artifacts = run_entrypoint(
        repo_url=None,
        ref=None,
        resolved_commit=None,
        entrypoint=[
            sys.executable,
            "-c",
            (
                "import json, os, urllib.request; "
                "uri=os.environ['MLFLOW_TRACKING_URI']; "
                "body=urllib.request.urlopen(uri + '/api/2.0/mlflow/experiments/list').read().decode('utf-8'); "
                "print(json.dumps({'uri': uri, 'cf_id': os.environ.get('CF_ACCESS_CLIENT_ID', ''), "
                "'cf_secret': os.environ.get('CF_ACCESS_CLIENT_SECRET', ''), 'body': body}))"
            ),
        ],
        run_mode="inline",
        env={
            "MLFLOW_TRACKING_URI": upstream,
            "CF_ACCESS_CLIENT_ID": "worker-id",
            "CF_ACCESS_CLIENT_SECRET": "worker-secret",
        },
        engine="discoverex",
        config_rel_path=None,
        inputs={"contract_version": "v2", "command": "generate"},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-mlflow-proxy",
    )
    try:
        assert artifacts.exit_code == 0
        payload = json.loads(artifacts.stdout_path.read_text(encoding="utf-8").strip())
        assert payload["uri"].startswith("http://127.0.0.1:")
        assert payload["uri"] != upstream
        assert payload["cf_id"] == ""
        assert payload["cf_secret"] == ""
        assert payload["body"] == '{"ok": true}'
        assert seen == {
            "cf_id": "worker-id",
            "cf_secret": "worker-secret",
        }
    finally:
        cleanup_workdir(artifacts.workdir)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_run_entrypoint_proxies_mlflow_via_worker_router() -> None:
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
    upstream = f"http://127.0.0.1:{server.server_address[1]}"
    artifacts = run_entrypoint(
        repo_url=None,
        ref=None,
        resolved_commit=None,
        entrypoint=[
            sys.executable,
            "-c",
            (
                "import json, os, urllib.request; "
                "uri=os.environ['MLFLOW_TRACKING_URI']; "
                "body=urllib.request.urlopen(uri + '/api/2.0/mlflow/experiments/list').read().decode('utf-8'); "
                "print(json.dumps({'uri': uri, 'body': body}))"
            ),
        ],
        run_mode="inline",
        env={
            "MLFLOW_TRACKING_URI": upstream,
            "CF_ACCESS_CLIENT_ID": "worker-id",
            "CF_ACCESS_CLIENT_SECRET": "worker-secret",
        },
        engine="discoverex",
        config_rel_path=None,
        inputs={"contract_version": "v2", "command": "generate"},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-mlflow-proxy",
    )
    try:
        assert artifacts.exit_code == 0
        payload = json.loads(artifacts.stdout_path.read_text(encoding="utf-8").strip())
        assert payload["uri"].startswith("http://127.0.0.1:")
        assert payload["body"] == '{"ok": true}'
        assert seen == {"cf_id": "worker-id", "cf_secret": "worker-secret"}
    finally:
        cleanup_workdir(artifacts.workdir)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_run_entrypoint_does_not_enable_mlflow_proxy_without_tracking_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    artifacts = run_entrypoint(
        repo_url=None,
        ref=None,
        resolved_commit=None,
        entrypoint=[
            sys.executable,
            "-c",
            "import os; print(os.environ.get('MLFLOW_TRACKING_URI', ''))",
        ],
        run_mode="inline",
        env={
            "CF_ACCESS_CLIENT_ID": "worker-id",
            "CF_ACCESS_CLIENT_SECRET": "worker-secret",
        },
        engine="discoverex",
        config_rel_path=None,
        inputs={"contract_version": "v2", "command": "generate"},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-no-mlflow-proxy",
    )
    try:
        assert artifacts.exit_code == 0
        assert artifacts.stdout_path.read_text(encoding="utf-8").strip() == ""
    finally:
        cleanup_workdir(artifacts.workdir)
