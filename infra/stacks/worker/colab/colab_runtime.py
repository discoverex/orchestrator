from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from common.prefect_client_env import apply_prefect_client_env

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"
DEFAULT_PID_PATH = Path("/tmp/orchestrator-colab-worker.pid")
DEFAULT_LOG_PATH = Path("/tmp/orchestrator-colab-worker.log")
DEFAULT_DRIVE_ROOT = Path("/content/drive/MyDrive/discoverex")
DEFAULT_REPO_DIR = DEFAULT_DRIVE_ROOT / "orchestrator"
DEFAULT_CACHE_ROOT = DEFAULT_DRIVE_ROOT / "cache"
DEFAULT_CHECKPOINT_DIR = Path("/content/drive/MyDrive/orchestrator/checkpoints")
DEFAULT_BOOTSTRAP_PYTHON = "python3"
REQUIRED_ENV = (
    "PREFECT_API_URL",
    "PREFECT_WORK_POOL",
    "STORAGE_GATEWAY_URL",
    "STORAGE_GATEWAY_TOKEN",
)


@dataclass(frozen=True)
class ColabRuntimeConfig:
    repo_dir: Path
    cache_root: Path
    checkpoint_dir: Path
    pid_file: Path
    log_file: Path
    python_bin: str = DEFAULT_BOOTSTRAP_PYTHON


def clean_env_value(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.strip()
    if (
        len(normalized) >= 2
        and normalized[0] == normalized[-1]
        and normalized[0] in ("'", '"')
    ):
        normalized = normalized[1:-1].strip()
    return normalized


def load_dotenv(env_path: Path | None = None) -> None:
    candidate = env_path or DEFAULT_ENV_PATH
    if not candidate.exists():
        return
    for raw in candidate.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _read_secret(
    key: str, secret_reader: Callable[[str], str | None] | None = None
) -> str | None:
    if secret_reader is None:
        return None
    try:
        return secret_reader(key)
    except Exception:
        return None


def populate_colab_env(
    config: ColabRuntimeConfig,
    *,
    secret_reader: Callable[[str], str | None] | None = None,
) -> dict[str, object]:
    defaults = {
        "PREFECT_API_URL": "https://prefect-api.discoverex.qzz.io/api",
        "PREFECT_WORK_POOL": "gpu-pool",
        "PREFECT_WORK_QUEUE": "gpu-colab",
        "ORCHESTRATOR_CHECKPOINT_DIR": str(config.checkpoint_dir),
        "PIP_CACHE_DIR": str(config.cache_root / "pip"),
        "XDG_CACHE_HOME": str(config.cache_root / "xdg"),
    }
    optional_keys = (
        "PREFECT_CF_ACCESS_CLIENT_ID",
        "PREFECT_CF_ACCESS_CLIENT_SECRET",
        "CF_ACCESS_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
        "STORAGE_GATEWAY_TOKEN",
        "STORAGE_GATEWAY_URL",
    )

    os.environ["PYTHONPATH"] = str(config.repo_dir / "src")
    os.environ["PIP_CACHE_DIR"] = defaults["PIP_CACHE_DIR"]
    os.environ["XDG_CACHE_HOME"] = defaults["XDG_CACHE_HOME"]

    config.cache_root.mkdir(parents=True, exist_ok=True)
    (config.cache_root / "pip").mkdir(parents=True, exist_ok=True)
    (config.cache_root / "xdg").mkdir(parents=True, exist_ok=True)

    for key, default in defaults.items():
        current = clean_env_value(os.environ.get(key))
        if current:
            os.environ[key] = current
            continue
        secret_value = clean_env_value(_read_secret(key, secret_reader))
        os.environ[key] = secret_value or default

    for key in optional_keys:
        current = clean_env_value(os.environ.get(key))
        if current:
            os.environ[key] = current
            continue
        secret_value = clean_env_value(_read_secret(key, secret_reader))
        if secret_value:
            os.environ[key] = secret_value

    for key in (*defaults.keys(), *optional_keys):
        if key in os.environ:
            os.environ[key] = clean_env_value(os.environ.get(key))

    cf_id = os.environ.get("PREFECT_CF_ACCESS_CLIENT_ID") or os.environ.get(
        "CF_ACCESS_CLIENT_ID"
    )
    cf_secret = os.environ.get("PREFECT_CF_ACCESS_CLIENT_SECRET") or os.environ.get(
        "CF_ACCESS_CLIENT_SECRET"
    )
    if cf_id and cf_secret:
        os.environ["PREFECT_CLIENT_CUSTOM_HEADERS"] = json.dumps(
            {
                "CF-Access-Client-Id": cf_id,
                "CF-Access-Client-Secret": cf_secret,
            },
            ensure_ascii=True,
        )
    else:
        os.environ.pop("PREFECT_CLIENT_CUSTOM_HEADERS", None)

    return runtime_snapshot(config)


def runtime_snapshot(config: ColabRuntimeConfig) -> dict[str, object]:
    cf_id = os.environ.get("PREFECT_CF_ACCESS_CLIENT_ID") or os.environ.get(
        "CF_ACCESS_CLIENT_ID"
    )
    cf_secret = os.environ.get("PREFECT_CF_ACCESS_CLIENT_SECRET") or os.environ.get(
        "CF_ACCESS_CLIENT_SECRET"
    )
    return {
        **asdict(config),
        "repo_dir": str(config.repo_dir),
        "cache_root": str(config.cache_root),
        "checkpoint_dir": str(config.checkpoint_dir),
        "pid_file": str(config.pid_file),
        "log_file": str(config.log_file),
        "prefect_api_url": os.environ.get("PREFECT_API_URL", ""),
        "prefect_work_pool": os.environ.get("PREFECT_WORK_POOL", ""),
        "prefect_work_queue": os.environ.get("PREFECT_WORK_QUEUE", ""),
        "has_cf_access_id": bool(cf_id),
        "has_cf_access_secret": bool(cf_secret),
        "has_prefect_custom_headers": bool(
            os.environ.get("PREFECT_CLIENT_CUSTOM_HEADERS")
        ),
        "has_storage_gateway_url": bool(os.environ.get("STORAGE_GATEWAY_URL")),
        "has_storage_gateway_token": bool(os.environ.get("STORAGE_GATEWAY_TOKEN")),
    }


def prefect_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    repo_src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = f"{repo_src}:{pythonpath}" if pythonpath else repo_src
    return apply_prefect_client_env(env, default_queue="gpu-colab")


def require_env() -> None:
    missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            f"missing required environment variables: {', '.join(missing)}"
        )
