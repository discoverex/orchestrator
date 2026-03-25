from __future__ import annotations

import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path
from socketserver import ThreadingMixIn


class _ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def test_dummy_engine_example_writes_manifest_and_artifacts(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            calls.append((self.path, payload))
            if self.path.endswith("/runs/create"):
                body = {"run": {"info": {"run_id": "mlflow-123"}}}
            else:
                body = {}
            raw = json.dumps(body, ensure_ascii=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            raw = json.dumps(
                {"run": {"info": {"run_id": "mlflow-123"}}}, ensure_ascii=True
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = _ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    artifact_dir = tmp_path / "artifacts"
    manifest_path = tmp_path / "engine-artifacts.manifest.json"
    proc = subprocess.run(
        [sys.executable, "tests/fixtures/dummy_engine_repo/src/dummy_engine/main.py"],
        cwd=Path(__file__).resolve().parents[2],
        env={
            "ORCH_ENGINE_ARTIFACT_DIR": str(artifact_dir),
            "ORCH_ENGINE_ARTIFACT_MANIFEST_PATH": str(manifest_path),
            "ORCH_FLOW_RUN_ID": "flow-123",
            "ORCH_JOB_NAME": "dummy-engine-smoke",
            "ORCH_JOB_INPUTS_JSON": json.dumps(
                {"scene_id": "scene-1", "version_id": "ver-1"}, ensure_ascii=True
            ),
            "MLFLOW_TRACKING_URI": f"http://127.0.0.1:{server.server_address[1]}",
            "PATH": str(Path(sys.executable).parent),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    try:
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout.strip())
        assert payload["scene_id"] == "scene-1"
        assert payload["version_id"] == "ver-1"
        assert payload["mlflow_run_id"] == "mlflow-123"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["schema_version"] == 1
        assert manifest["artifacts"][0]["logical_name"] == "scene_json"
        scene = json.loads((artifact_dir / "scene" / "scene.json").read_text())
        assert scene["flow_run_id"] == "flow-123"
        verification = json.loads(
            (artifact_dir / "scene" / "verification.json").read_text()
        )
        assert verification["status"] == "ok"
        assert calls[0][0] == "/api/2.0/mlflow/runs/create"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
