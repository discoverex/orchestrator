from __future__ import annotations

from pathlib import Path


def test_caddyfile_has_https_redirect_and_reverse_proxy() -> None:
    caddyfile = Path("infra/stacks/prefect-server/Caddyfile").read_text(encoding="utf-8")

    assert "email {$CADDY_ACME_EMAIL}" not in caddyfile
    assert "http://{$PREFECT_HOSTNAMES}" in caddyfile
    assert "redir https://{host}{uri} permanent" in caddyfile
    assert "https://{$PREFECT_HOSTNAMES}" in caddyfile
    assert "reverse_proxy prefect-server:{$PREFECT_PORT}" in caddyfile
