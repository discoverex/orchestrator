#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.e2e.lib import verify_remote_chain_core as core  # noqa: E402

VerifyError = core.VerifyError


def _print_json(payload: dict[str, Any]) -> None:
    core.print_json(payload)


def _http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any] | list[dict[str, Any]]:
    return core.http_json(
        method, url, payload=payload, headers=headers, timeout=timeout
    )


def _run_ops_script(
    script_rel_path: str, env_overrides: dict[str, str], argv: list[str]
) -> dict[str, Any]:
    return core.run_ops_script(script_rel_path, env_overrides, argv)


def _command_wait_completed(args: argparse.Namespace) -> dict[str, Any]:
    return core.command_wait_completed(args, _http_json)


def _command_storage_objects(args: argparse.Namespace) -> dict[str, Any]:
    return core.command_storage_objects(args, _http_json)


def _command_flush_verify(args: argparse.Namespace) -> dict[str, Any]:
    return core.command_flush_verify(args, _run_ops_script)


def _command_prune_verify(args: argparse.Namespace) -> dict[str, Any]:
    return core.command_prune_verify(args, _run_ops_script, _http_json)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remote Prefect/storage verification helpers for E2E."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    wait_p = sub.add_parser("prefect-wait-completed")
    wait_p.add_argument("--prefect-api-url", required=True)
    wait_p.add_argument("--flow-run-id", required=True)
    wait_p.add_argument("--timeout-sec", type=int, default=600)
    wait_p.add_argument("--poll-interval-sec", type=int, default=2)
    wait_p.add_argument("--prefect-cf-access-client-id")
    wait_p.add_argument("--prefect-cf-access-client-secret")

    storage_p = sub.add_parser("storage-objects")
    storage_p.add_argument("--storage-api-url", required=True)
    storage_p.add_argument("--prefect-cf-access-client-id")
    storage_p.add_argument("--prefect-cf-access-client-secret")
    storage_p.add_argument("--artifact-bucket", required=True)
    storage_p.add_argument("--flow-run-id", required=True)
    storage_p.add_argument("--attempt", type=int, default=1)
    storage_p.add_argument("--output-json")

    flush_p = sub.add_parser("flush-verify")
    flush_p.add_argument("--prefect-api-url", required=True)
    flush_p.add_argument("--storage-api-url", required=True)
    flush_p.add_argument("--flow-run-id", required=True)
    flush_p.add_argument("--cursor-path", required=True)
    flush_p.add_argument("--page-size", type=int, default=100)
    flush_p.add_argument("--max-runs", type=int, default=500)
    flush_p.add_argument("--prefect-cf-access-client-id")
    flush_p.add_argument("--prefect-cf-access-client-secret")

    prune_p = sub.add_parser("prune-verify")
    prune_p.add_argument("--prefect-api-url", required=True)
    prune_p.add_argument("--flow-run-id", required=True)
    prune_p.add_argument("--apply", action="store_true")
    prune_p.add_argument("--ttl-hours", type=int, default=72)
    prune_p.add_argument("--page-size", type=int, default=200)
    prune_p.add_argument("--max-runs", type=int, default=1000)
    prune_p.add_argument("--prefect-cf-access-client-id")
    prune_p.add_argument("--prefect-cf-access-client-secret")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        if args.command == "prefect-wait-completed":
            out = _command_wait_completed(args)
        elif args.command == "storage-objects":
            out = _command_storage_objects(args)
        elif args.command == "flush-verify":
            out = _command_flush_verify(args)
        elif args.command == "prune-verify":
            out = _command_prune_verify(args)
        else:
            raise VerifyError(
                "main", "UNKNOWN_COMMAND", f"unsupported command: {args.command}"
            )
    except VerifyError as exc:
        _print_json(exc.as_json())
        return 1
    except Exception as exc:  # noqa: BLE001
        _print_json(
            {
                "ok": False,
                "step": "unhandled",
                "error_code": "UNHANDLED_EXCEPTION",
                "error_message": str(exc),
            }
        )
        return 1

    _print_json(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
