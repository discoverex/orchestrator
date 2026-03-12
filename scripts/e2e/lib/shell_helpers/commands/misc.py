from __future__ import annotations

import argparse
import json


def cmd_build_cf_headers_json(args: argparse.Namespace) -> int:
    print(
        json.dumps(
            {
                "CF-Access-Client-Id": args.client_id,
                "CF-Access-Client-Secret": args.client_secret,
            },
            ensure_ascii=True,
        )
    )
    return 0
