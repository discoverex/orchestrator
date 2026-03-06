from __future__ import annotations

import pytest

from flows.job_spec import JobSpecError, parse_job_spec_json


def test_parse_job_spec_json_accepts_valid_payload() -> None:
    raw = '{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo ok"],"config":"configs/run.yaml","inputs":{},"env":{},"outputs_prefix":null}'
    spec = parse_job_spec_json(raw)
    assert spec.engine == "shell"
    assert spec.config == "configs/run.yaml"


def test_parse_job_spec_json_rejects_path_escape() -> None:
    raw = '{"engine":"shell","repo_url":"https://github.com/octocat/Hello-World.git","ref":"master","entrypoint":["/bin/sh","-lc","echo ok"],"config":"../secret.yaml","inputs":{},"env":{},"outputs_prefix":null}'
    with pytest.raises(JobSpecError):
        parse_job_spec_json(raw)
