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
                "deployments:",
                "  - name: fixed-primary",
                "    work_queue: queue-fixed",
                "    mode: primary",
                "    role: fixed",
                "  - name: colab-primary",
                "    work_queue: queue-colab",
                "    mode: primary",
                "    role: colab",
                "  - name: fixed-compat",
                "    work_queue: queue-fixed",
                "    mode: compat",
                "    role: fixed",
                "  - name: colab-compat",
                "    work_queue: queue-colab",
                "    mode: compat",
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
        compat_fixed_name=None,
        compat_fixed_queue=None,
        compat_colab_name=None,
        compat_colab_queue=None,
        register_compat_aliases=True,
        flow_source="/srv/engine",
        flow_entrypoint=None,
        version=None,
    )

    specs = support.iter_specs(args)
    target = support.resolve_target(args)

    assert [(spec.name, spec.work_queue_name) for spec in specs] == [
        ("fixed-primary", "queue-fixed"),
        ("colab-primary", "queue-colab"),
        ("fixed-compat", "queue-fixed"),
        ("colab-compat", "queue-colab"),
    ]
    assert target.entrypoint == "src/flows/worker_runtime/flow.py:run_worker_job_flow"
