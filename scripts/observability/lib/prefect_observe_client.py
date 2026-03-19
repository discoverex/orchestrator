from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request


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
            with request.urlopen(req, timeout=timeout) as resp:
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
        parameters: dict[str, Any],
        flow_run_name: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"parameters": parameters}
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
        return [row for row in out if isinstance(row, dict)]

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
