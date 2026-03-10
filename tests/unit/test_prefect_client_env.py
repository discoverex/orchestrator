from __future__ import annotations

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
