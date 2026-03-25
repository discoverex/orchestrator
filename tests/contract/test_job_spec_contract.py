from __future__ import annotations

import pytest

from flows.job_spec import JobSpecError, parse_job_spec_json


def test_parse_job_spec_json_accepts_valid_payload() -> None:
    raw = (
        '{"engine":"shell",'
        '"repo_url":"https://github.com/octocat/Hello-World.git",'
        '"ref":"master",'
        '"entrypoint":["/bin/sh","-lc","echo ok"],'
        '"config":"configs/run.yaml",'
        '"inputs":{},'
        '"env":{},'
        '"outputs_prefix":null}'
    )
    spec = parse_job_spec_json(raw)
    assert spec.engine == "shell"
    assert spec.run_mode == "repo"
    assert spec.config == "configs/run.yaml"


def test_parse_job_spec_json_rejects_path_escape() -> None:
    raw = (
        '{"engine":"shell",'
        '"repo_url":"https://github.com/octocat/Hello-World.git",'
        '"ref":"master",'
        '"entrypoint":["/bin/sh","-lc","echo ok"],'
        '"config":"../secret.yaml",'
        '"inputs":{},'
        '"env":{},'
        '"outputs_prefix":null}'
    )
    with pytest.raises(JobSpecError):
        parse_job_spec_json(raw)


def test_parse_job_spec_json_accepts_inline_mode_without_repo() -> None:
    raw = (
        '{"run_mode":"inline",'
        '"engine":"shell",'
        '"entrypoint":["/bin/sh","-lc","nvidia-smi"],'
        '"config":null,'
        '"inputs":{},'
        '"env":{},'
        '"outputs_prefix":null}'
    )
    spec = parse_job_spec_json(raw)
    assert spec.run_mode == "inline"
    assert spec.repo_url is None
    assert spec.ref is None


def test_parse_job_spec_json_rejects_repo_mode_without_repo_fields() -> None:
    raw = (
        '{"run_mode":"repo",'
        '"engine":"shell",'
        '"entrypoint":["/bin/sh","-lc","echo ok"],'
        '"config":null,'
        '"inputs":{},'
        '"env":{},"outputs_prefix":null}'
    )
    with pytest.raises(JobSpecError):
        parse_job_spec_json(raw)
