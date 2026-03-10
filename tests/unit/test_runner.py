from __future__ import annotations

import http.server
import json
import sys
import threading
from pathlib import Path
from socketserver import ThreadingMixIn

import pytest

from runner import git_runner
from runner.git_runner import (
    RunnerError,
    cleanup_workdir,
    resolve_commit,
    run_entrypoint,
)


def test_resolve_commit_accepts_sha() -> None:
    sha = "a" * 40
    assert resolve_commit("https://example.com/repo.git", sha) == sha


def test_resolve_commit_invalid_ref_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _always_fail(_cmd: list[str], cwd: Path | None = None) -> str:
        _ = cwd
        raise RunnerError("fail")

    monkeypatch.setattr(git_runner, "_run", _always_fail)
    with pytest.raises(RunnerError):
        resolve_commit("https://invalid.invalid/repo.git", "main")


def test_resolve_commit_uses_safe_directory_for_local_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    (tmp_path / ".git").mkdir()

    def _fake_run(cmd: list[str], cwd: Path | None = None) -> str:
        _ = cwd
        calls.append(cmd)
        return "b" * 40

    monkeypatch.setattr(git_runner, "_run", _fake_run)
    out = resolve_commit(str(tmp_path), "HEAD")
    assert out == "b" * 40
    assert calls == [
        [
            "git",
            "-c",
            f"safe.directory={tmp_path.resolve()}",
            "-c",
            f"safe.directory={tmp_path.resolve() / '.git'}",
            "-C",
            str(tmp_path),
            "rev-parse",
            "HEAD",
        ]
    ]


def test_resolve_commit_normalizes_github_ssh_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], cwd: Path | None = None) -> str:
        _ = cwd
        calls.append(cmd)
        return "c" * 40

    monkeypatch.setattr(git_runner, "_run", _fake_run)
    out = resolve_commit("git@github.com:discoverex/engine.git", "dev")
    assert out == "c" * 40
    assert calls == [
        [
            "git",
            "ls-remote",
            "https://github.com/discoverex/engine.git",
            "refs/heads/dev",
        ]
    ]


def test_prepare_cached_repo_removes_broken_cache_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("ORCH_REPO_CACHE_DIR", str(cache_root))
    broken_cache = git_runner._repo_cache_path(
        "https://github.com/discoverex/engine.git"
    )
    broken_cache.mkdir(parents=True)
    calls: list[tuple[list[str], Path | None]] = []

    def _fake_run(cmd: list[str], cwd: Path | None = None) -> str:
        calls.append((cmd, cwd))
        if cmd[:3] == ["git", "clone", "--filter=blob:none"]:
            target = Path(cmd[-1])
            (target / ".git").mkdir(parents=True, exist_ok=True)
        return ""

    monkeypatch.setattr(git_runner, "_run", _fake_run)

    repo = git_runner._prepare_cached_repo(
        "git@github.com:discoverex/engine.git",
        "dev",
        "a" * 40,
    )

    assert repo == broken_cache
    assert (broken_cache / ".git").exists()
    assert calls[0] == (
        [
            "git",
            "clone",
            "--filter=blob:none",
            "https://github.com/discoverex/engine.git",
            str(broken_cache),
        ],
        None,
    )


def test_checkout_target_prefers_named_ref() -> None:
    assert git_runner._checkout_target("dev", "a" * 40) == "dev"
    assert (
        git_runner._checkout_target("refs/tags/v1.0.0", "a" * 40) == "refs/tags/v1.0.0"
    )
    assert git_runner._checkout_target("a" * 40, "b" * 40) == "b" * 40
    assert git_runner._checkout_target(None, "b" * 40) == "b" * 40


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
            "printf '%s\\n' \"$ORCH_JOB_INPUTS_JSON\" > inputs.json && printf '%s' \"$MLFLOW_TRACKING_URI\"",
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
    finally:
        cleanup_workdir(artifacts.workdir)


class _ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def test_run_entrypoint_proxies_remote_mlflow_with_worker_auth() -> None:
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
            "MLFLOW_TRACKING_URI": "https://mlflow.discoverex.qzz.io",
            "WORKER_ROUTER_URL": upstream,
            "CF_ACCESS_CLIENT_ID": "worker-id",
            "CF_ACCESS_CLIENT_SECRET": "worker-secret",
        },
        engine="discoverex",
        config_rel_path=None,
        inputs={"contract_version": "v2", "command": "generate"},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-mlflow-router",
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
            "WORKER_ROUTER_URL": "https://discoverex.qzz.io",
            "CF_ACCESS_CLIENT_ID": "worker-id",
            "CF_ACCESS_CLIENT_SECRET": "worker-secret",
        },
        engine="discoverex",
        config_rel_path=None,
        inputs={"contract_version": "v2", "command": "generate"},
        flow_run_id="flow-inline",
        attempt=1,
        outputs_prefix="jobs/flow-inline/attempt-1/",
        job_name="inline-no-mlflow-router",
    )
    try:
        assert artifacts.exit_code == 0
        assert artifacts.stdout_path.read_text(encoding="utf-8").strip() == ""
    finally:
        cleanup_workdir(artifacts.workdir)
