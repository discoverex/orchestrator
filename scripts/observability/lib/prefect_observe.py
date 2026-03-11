from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = ROOT_DIR / ".env"


class ObserveError(RuntimeError):
    """Raised when an observability command cannot complete."""


@dataclass(frozen=True)
class PrefectObserveClient:
    api_url: str
    headers: dict[str, str]

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int = 30,
    ) -> Any:
        url = f"{self.api_url}/{path.lstrip('/')}"
        body = None
        headers = dict(self.headers)
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(url, method=method, data=body, headers=headers)
        try:
            with request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                raw = resp.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ObserveError(
                f"{method} {path} failed: HTTP {exc.code} {detail}"
            ) from exc
        except error.URLError as exc:
            raise ObserveError(f"{method} {path} unreachable: {exc.reason}") from exc
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def health(self) -> bool:
        out = self.request_json("GET", "health")
        if isinstance(out, bool):
            return out
        raise ObserveError(f"unexpected health response: {out!r}")

    def find_deployment(self, name: str) -> dict[str, Any]:
        rows = self.request_json(
            "POST",
            "deployments/filter",
            {
                "sort": "NAME_ASC",
                "limit": 50,
                "offset": 0,
                "deployments": {"name": {"any_": [name]}},
            },
        )
        if not isinstance(rows, list):
            raise ObserveError("unexpected deployments/filter response shape")
        for row in rows:
            if isinstance(row, dict) and str(row.get("name", "")) == name:
                return row
        raise ObserveError(f"deployment not found: {name}")

    def create_flow_run(
        self,
        deployment_id: str,
        *,
        job_spec_raw: str,
        flow_run_name: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"parameters": {"job_spec_json": job_spec_raw}}
        if flow_run_name:
            payload["name"] = flow_run_name
        out = self.request_json(
            "POST", f"deployments/{deployment_id}/create_flow_run", payload
        )
        if not isinstance(out, dict):
            raise ObserveError("unexpected create_flow_run response shape")
        return out

    def get_flow_run(self, flow_run_id: str) -> dict[str, Any]:
        out = self.request_json("GET", f"flow_runs/{flow_run_id}")
        if not isinstance(out, dict):
            raise ObserveError("unexpected flow_runs/{id} response shape")
        return out

    def list_workers(self, work_pool: str, limit: int = 20) -> list[dict[str, Any]]:
        out = self.request_json(
            "POST",
            f"work_pools/{work_pool}/workers/filter",
            {"limit": limit, "offset": 0},
        )
        if not isinstance(out, list):
            raise ObserveError("unexpected workers/filter response shape")
        rows = [row for row in out if isinstance(row, dict)]
        return rows

    def ensure_work_pool(self, name: str, pool_type: str = "process") -> dict[str, Any]:
        try:
            out = self.request_json("GET", f"work_pools/{name}")
        except ObserveError as exc:
            if "HTTP 404" not in str(exc):
                raise
            out = self.request_json(
                "POST",
                "work_pools/",
                {
                    "name": name,
                    "type": pool_type,
                    "base_job_template": {},
                    "is_paused": False,
                },
            )
        if not isinstance(out, dict):
            raise ObserveError("unexpected work_pools response shape")
        return out


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
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
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


def load_job_spec(path: str) -> str:
    raw = Path(path).read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ObserveError("job spec file must contain a JSON object")
    return json.dumps(parsed, ensure_ascii=True)


def summarize_deployment(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "work_pool_name": row.get("work_pool_name"),
        "work_queue_name": row.get("work_queue_name"),
        "created": row.get("created"),
        "updated": row.get("updated"),
    }


def summarize_flow_run(row: dict[str, Any]) -> dict[str, Any]:
    state = row.get("state")
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "deployment_id": row.get("deployment_id"),
        "work_queue_name": row.get("work_queue_name"),
        "state_type": row.get("state_type") or (state or {}).get("type"),
        "state_name": row.get("state_name") or (state or {}).get("name"),
        "state_message": (state or {}).get("message") if isinstance(state, dict) else None,
        "created": row.get("created"),
        "expected_start_time": row.get("expected_start_time"),
        "start_time": row.get("start_time"),
        "end_time": row.get("end_time"),
        "infrastructure_pid": row.get("infrastructure_pid"),
    }


def poll_flow_run(
    client: PrefectObserveClient,
    flow_run_id: str,
    *,
    timeout_sec: int = 180,
    poll_interval_sec: int = 5,
) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last: dict[str, Any] | None = None
    while time.time() < deadline:
        current = client.get_flow_run(flow_run_id)
        last = current
        state_type = str(
            current.get("state_type") or current.get("state", {}).get("type") or ""
        ).upper()
        if state_type in {"COMPLETED", "FAILED", "CRASHED", "CANCELLED"}:
            return current
        time.sleep(poll_interval_sec)
    if last is None:
        raise ObserveError("flow run polling produced no response")
    raise ObserveError(
        f"timed out waiting for terminal state: {summarize_flow_run(last)}"
    )


def print_json(payload: dict[str, Any] | list[dict[str, Any]] | bool) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2))
