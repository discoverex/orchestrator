from __future__ import annotations

import contextlib
import http.server
import socketserver
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from urllib import error, request
from urllib.parse import urlsplit


def _is_remote_http_url(url: str) -> bool:
    scheme = urlsplit(url).scheme.lower()
    return scheme in {"http", "https"}


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@dataclass
class MLflowProxy:
    upstream_url: str
    cf_access_client_id: str
    cf_access_client_secret: str
    bind_host: str = "127.0.0.1"

    def __post_init__(self) -> None:
        self._server = _ThreadingHTTPServer((self.bind_host, 0), self._handler_class())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="mlflow-cf-proxy",
            daemon=True,
        )

    @property
    def local_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def _handler_class(self) -> type[http.server.BaseHTTPRequestHandler]:
        upstream_url = self.upstream_url.rstrip("/")
        cf_id = self.cf_access_client_id
        cf_secret = self.cf_access_client_secret

        class ProxyHandler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                self._forward()

            def do_POST(self) -> None:  # noqa: N802
                self._forward()

            def do_PUT(self) -> None:  # noqa: N802
                self._forward()

            def do_PATCH(self) -> None:  # noqa: N802
                self._forward()

            def do_DELETE(self) -> None:  # noqa: N802
                self._forward()

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _forward(self) -> None:
                body = b""
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length > 0:
                    body = self.rfile.read(length)
                target = f"{upstream_url}{self.path}"
                headers = {
                    key: value
                    for key, value in self.headers.items()
                    if key.lower() not in {"host", "content-length"}
                }
                headers["CF-Access-Client-Id"] = cf_id
                headers["CF-Access-Client-Secret"] = cf_secret
                req = request.Request(
                    target,
                    method=self.command,
                    data=body or None,
                    headers=headers,
                )
                try:
                    with request.urlopen(req, timeout=60) as resp:  # nosec B310
                        payload = resp.read()
                        self.send_response(resp.status)
                        for key, value in resp.headers.items():
                            if key.lower() in {"transfer-encoding", "content-length"}:
                                continue
                            self.send_header(key, value)
                        self.send_header("Content-Length", str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                except error.HTTPError as exc:
                    payload = exc.read()
                    self.send_response(exc.code)
                    for key, value in exc.headers.items():
                        if key.lower() in {"transfer-encoding", "content-length"}:
                            continue
                        self.send_header(key, value)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)

        return ProxyHandler


@contextlib.contextmanager
def maybe_start_mlflow_proxy(env: dict[str, str]) -> Iterator[dict[str, str]]:
    tracking_uri = env.get("MLFLOW_TRACKING_URI", "").strip()
    cf_id = env.get("CF_ACCESS_CLIENT_ID", "").strip()
    cf_secret = env.get("CF_ACCESS_CLIENT_SECRET", "").strip()
    if (
        not tracking_uri
        or not _is_remote_http_url(tracking_uri)
        or not cf_id
        or not cf_secret
    ):
        yield env
        return

    proxy = MLflowProxy(
        upstream_url=tracking_uri,
        cf_access_client_id=cf_id,
        cf_access_client_secret=cf_secret,
    )
    proxy.start()
    proxied_env = env.copy()
    proxied_env["MLFLOW_TRACKING_URI"] = proxy.local_url
    proxied_env["ORCH_REMOTE_MLFLOW_TRACKING_URI"] = tracking_uri
    proxied_env.pop("CF_ACCESS_CLIENT_ID", None)
    proxied_env.pop("CF_ACCESS_CLIENT_SECRET", None)
    try:
        yield proxied_env
    finally:
        proxy.close()
