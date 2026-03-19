from __future__ import annotations

import os

from common.prefect.client_env import apply_prefect_client_env


def run() -> int:
    os.environ.update(apply_prefect_client_env(dict(os.environ)))
    from common.prefect.work_queues import ensure_work_pool_and_queues
    from deployments.register.main import main, parse_args
    from deployments.register.support import iter_specs

    args = parse_args()
    for spec in iter_specs(args):
        ensure_work_pool_and_queues(
            args.pool,
            primary_queue=spec.work_queue_name,
        )
    main()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
