from __future__ import annotations

from pathlib import Path

FORBIDDEN_CLI_PATTERNS = (
    "docker compose ",
    "docker build ",
    "ssh -i ",
    "python3 ",
    "curl -fsS ",
)


def _script_paths(root: str) -> list[Path]:
    return sorted(Path(root).rglob("cli.sh"))


def _runtime_script_content(path: Path) -> str:
    lines: list[str] = []
    in_heredoc = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if "cat <<'EOF'" in raw_line:
            in_heredoc = True
            continue
        if in_heredoc:
            if stripped == "EOF":
                in_heredoc = False
            continue
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def test_cli_scripts_do_not_execute_low_level_drivers_directly() -> None:
    roots = [
        "scripts/base",
        "scripts/local",
        "scripts/storage",
        "scripts/register",
        "scripts/prefect",
        "scripts/worker",
        "scripts/runtime",
        "scripts/e2e",
        "scripts/ops",
        "scripts/observability",
    ]

    for root in roots:
        for path in _script_paths(root):
            content = _runtime_script_content(path)
            for token in FORBIDDEN_CLI_PATTERNS:
                assert token not in content, (
                    f"{path} contains low-level driver token: {token}"
                )


def test_bin_cli_routes_to_domain_clis() -> None:
    content = Path("bin/cli").read_text(encoding="utf-8")

    assert "scripts/prefect/cli.sh" in content
    assert "scripts/worker/cli.sh" in content
    assert "scripts/observability/cli.sh" in content
    assert "scripts/base/cli.sh" in content
    assert "scripts/storage/cli.sh" in content
