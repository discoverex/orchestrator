from __future__ import annotations

from pathlib import Path


def test_caddyfile_has_https_redirect_and_reverse_proxy() -> None:
    caddyfile = Path("infra/stacks/prefect-server/Caddyfile").read_text(encoding="utf-8")

    assert "email {$CADDY_ACME_EMAIL}" not in caddyfile
    assert "http://{$PREFECT_HOSTNAME}" in caddyfile
    assert "redir https://{$PREFECT_HOSTNAME}{uri} permanent" in caddyfile
    assert "https://{$PREFECT_HOSTNAME}" in caddyfile
    assert "reverse_proxy prefect-server:{$PREFECT_PORT}" in caddyfile
