from __future__ import annotations

import argparse
from pathlib import Path

import deployments.register.support as support


def test_iter_specs_uses_yaml_catalog_defaults(tmp_path: Path) -> None:
    spec_file = tmp_path / "deployments.yaml"
    spec_file.write_text(
        "\n".join(
            [
                "version: 1",
                "flow:",
                "  name: e2e-job",
                "  source: src/flows/worker_runtime/flow.py",
                "  entrypoint: run_worker_job_flow",
                "  parameters:",
                "    run_mode: repo",
                "    engine: dummy-engine",
                "    repo_url: https://github.com/example/repo.git",
                "    ref: main",
                "    flow_entrypoint: src/dummy_engine/prefect_flow.py:dummy_engine_flow",
                "    config: null",
                "    job_name: null",
                "    inputs: {}",
                "    env: {}",
                "    outputs_prefix: null",
                "deployments:",
                "  - name: fixed-primary",
                "    work_queue: queue-fixed",
                "    mode: primary",
                "    role: fixed",
                "  - name: colab-primary",
                "    work_queue: queue-colab",
                "    mode: primary",
                "    role: colab",
            ]
        ),
        encoding="utf-8",
    )

    args = argparse.Namespace(
        single_name=None,
        single_queue="default",
        spec_file=str(spec_file),
        pool="gpu-pool",
        fixed_name=None,
        fixed_queue=None,
        colab_name=None,
        colab_queue=None,
        flow_source="/srv/engine",
        flow_entrypoint=None,
        version=None,
    )

    specs = support.iter_specs(args)
    target = support.resolve_target(args)

    assert [(spec.name, spec.work_queue_name) for spec in specs] == [
        ("fixed-primary", "queue-fixed"),
        ("colab-primary", "queue-colab"),
    ]
    assert target.entrypoint == "src/flows/worker_runtime/flow.py:run_worker_job_flow"
