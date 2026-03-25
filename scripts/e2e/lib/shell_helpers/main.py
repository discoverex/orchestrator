from __future__ import annotations

from .commands.misc import cmd_build_cf_headers_json
from .commands.mlflow import (
    cmd_create_and_verify_mlflow_tags,
    cmd_verify_engine_mlflow_run,
)
from .commands.prefect import (
    cmd_poll_prefect_completion,
    cmd_verify_prefect_priority,
    cmd_verify_prune_removed,
    cmd_wait_prefect_state,
)
from .commands.storage import (
    cmd_uri_host,
    cmd_verify_flush_output,
    cmd_verify_storage_objects,
)
from .commands.summary import cmd_write_summary_local, cmd_write_summary_remote
from .parser import build_parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "write-summary-local": cmd_write_summary_local,
        "poll-prefect-completion": cmd_poll_prefect_completion,
        "wait-prefect-state": cmd_wait_prefect_state,
        "verify-prefect-priority": cmd_verify_prefect_priority,
        "verify-storage-objects": cmd_verify_storage_objects,
        "create-and-verify-mlflow-tags": cmd_create_and_verify_mlflow_tags,
        "verify-engine-mlflow-run": cmd_verify_engine_mlflow_run,
        "uri-host": cmd_uri_host,
        "verify-flush-output": cmd_verify_flush_output,
        "verify-prune-removed": cmd_verify_prune_removed,
        "write-summary-remote": cmd_write_summary_remote,
        "build-cf-headers-json": cmd_build_cf_headers_json,
    }

    func = dispatch.get(args.command)
    if func:
        return func(args)
    return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
