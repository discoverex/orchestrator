from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import common.prefect_client_env as prefect_client_env
from common.prefect_client_env import (
    WorkerStartupSummary,
    apply_prefect_client_env,
    build_prefect_client_headers,
    shell_exports,
    startup_summary,
)


def test_apply_prefect_client_env_sets_default_queue() -> None:
    env = apply_prefect_client_env({}, default_queue="gpu-fixed")

    assert env["PREFECT_WORK_QUEUE"] == "gpu-fixed"
    assert "PREFECT_CLIENT_CUSTOM_HEADERS" not in env


def test_build_prefect_client_headers_maps_prefect_cf_headers() -> None:
    headers = build_prefect_client_headers(
        {
            "CF_ACCESS_CLIENT_ID": "prefect-id",
            "CF_ACCESS_CLIENT_SECRET": "prefect-secret",
        }
    )

    assert headers == {
        "CF-Access-Client-Id": "prefect-id",
        "CF-Access-Client-Secret": "prefect-secret",
    }


def test_build_prefect_client_headers_keeps_existing_custom_headers() -> None:
    headers = build_prefect_client_headers(
        {
            "PREFECT_CLIENT_CUSTOM_HEADERS": '{"X-Test":"1"}',
            "CF_ACCESS_CLIENT_ID": "prefect-id",
            "CF_ACCESS_CLIENT_SECRET": "prefect-secret",
        }
    )

    assert headers == {
        "X-Test": "1",
        "CF-Access-Client-Id": "prefect-id",
        "CF-Access-Client-Secret": "prefect-secret",
    }


def test_build_prefect_client_headers_ignores_invalid_json() -> None:
    headers = build_prefect_client_headers(
        {
            "PREFECT_CLIENT_CUSTOM_HEADERS": "{not-json}",
            "CF_ACCESS_CLIENT_ID": "prefect-id",
            "CF_ACCESS_CLIENT_SECRET": "prefect-secret",
        }
    )

    assert headers == {
        "CF-Access-Client-Id": "prefect-id",
        "CF-Access-Client-Secret": "prefect-secret",
    }


def test_shell_exports_emits_only_changed_values() -> None:
    exports = shell_exports(
        {
            "PREFECT_CLIENT_CUSTOM_HEADERS": '{"User-Agent":"custom-agent"}',
        },
        default_queue="gpu-fixed",
    ).splitlines()

    assert exports == [
        "export PREFECT_WORK_QUEUE=gpu-fixed",
        "unset PREFECT_CLIENT_CUSTOM_HEADERS",
    ]


def test_shell_exports_emits_custom_headers_when_changed() -> None:
    exports = shell_exports(
        {
            "CF_ACCESS_CLIENT_ID": "prefect-id",
            "CF_ACCESS_CLIENT_SECRET": "prefect-secret",
        },
        default_queue="gpu-fixed",
    ).splitlines()

    assert exports == [
        "export PREFECT_WORK_QUEUE=gpu-fixed",
        "export PREFECT_CLIENT_CUSTOM_HEADERS='{\"CF-Access-Client-Id\": \"prefect-id\", \"CF-Access-Client-Secret\": \"prefect-secret\"}'",
    ]


def test_startup_summary_masks_to_presence_not_secret_values() -> None:
    summary = startup_summary(
        {
            "PREFECT_API_URL": "https://prefect.example/api",
            "PREFECT_WORK_POOL": "gpu-pool",
            "CF_ACCESS_CLIENT_ID": "id",
            "CF_ACCESS_CLIENT_SECRET": "secret",
            "PREFECT_CLIENT_CUSTOM_HEADERS": '{"X-Test":"1","User-Agent":"ua"}',
        },
        default_queue="gpu-fixed",
    )

    assert summary == WorkerStartupSummary(
        prefect_api_url="https://prefect.example/api",
        prefect_work_pool="gpu-pool",
        prefect_work_queue="gpu-fixed",
        checkpoint_dir="",
        custom_header_keys=[
            "CF-Access-Client-Id",
            "CF-Access-Client-Secret",
            "X-Test",
        ],
        cf_access_configured=True,
    )


def test_startup_summary_ignores_invalid_custom_headers() -> None:
    summary = startup_summary(
        {
            "PREFECT_CLIENT_CUSTOM_HEADERS": "{bad-json}",
            "CF_ACCESS_CLIENT_ID": "id",
        }
    )

    assert summary.custom_header_keys == []
    assert summary.cf_access_configured is False


def test_main_shell_prints_exports(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        prefect_client_env,
        "_parse_args",
        lambda: SimpleNamespace(command="shell", default_queue="gpu-fixed"),
    )
    monkeypatch.setattr(
        prefect_client_env,
        "shell_exports",
        lambda **kwargs: "export PREFECT_WORK_QUEUE=gpu-fixed",
    )

    rc = prefect_client_env.main()

    assert rc == 0
    assert capsys.readouterr().out.strip() == "export PREFECT_WORK_QUEUE=gpu-fixed"


def test_main_summary_prints_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        prefect_client_env,
        "_parse_args",
        lambda: SimpleNamespace(command="summary", default_queue="gpu-fixed"),
    )
    monkeypatch.setattr(
        prefect_client_env,
        "startup_summary",
        lambda **kwargs: WorkerStartupSummary(
            prefect_api_url="https://prefect.example/api",
            prefect_work_pool="gpu-pool",
            prefect_work_queue="gpu-fixed",
            checkpoint_dir="/tmp/checkpoints",
            custom_header_keys=["X-Test"],
            cf_access_configured=True,
        ),
    )

    rc = prefect_client_env.main()

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["prefect_api_url"] == "https://prefect.example/api"
    assert payload["custom_header_keys"] == ["X-Test"]
