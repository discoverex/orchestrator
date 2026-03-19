from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.observability.lib.prefect_observe_client import (
    ObserveError,
    PrefectObserveClient,
)

ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = ROOT_DIR / ".env"


def load_env_file_if_exists(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def bootstrap_env(env_file: str | None = None) -> None:
    path = Path(env_file).resolve() if env_file else DEFAULT_ENV_FILE
    load_env_file_if_exists(path)


def build_client(env_file: str | None = None) -> PrefectObserveClient:
    bootstrap_env(env_file)
    api_url = os.getenv("PREFECT_API_URL", "").rstrip("/")
    if not api_url:
        raise ObserveError("missing PREFECT_API_URL")
    headers = {
        "Accept": "application/json",
        "User-Agent": "orchestrator-observability/1.0",
    }
    cf_id = os.getenv("CF_ACCESS_CLIENT_ID", "")
    cf_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "")
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return PrefectObserveClient(api_url=api_url, headers=headers)


def load_flow_parameters(path: str | None = None) -> dict[str, object]:
    if path:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return dict(payload)
    return {
        "run_mode": "inline",
        "engine": "fixed-dummy",
        "flow_entrypoint": "src/dummy_engine/prefect_flow.py:dummy_engine_flow",
        "inputs": {},
        "env": {},
        "outputs_prefix": None,
    }
