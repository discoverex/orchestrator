from __future__ import annotations

import pytest

from flows.adapters.inbound.schema import load_parameters_json
from flows.domain.run_request import RunRequestError


def test_load_parameters_json_accepts_valid_payload() -> None:
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
    request = load_parameters_json(raw)
    assert request.engine == "shell"
    assert request.run_mode == "repo"
    assert request.config == "configs/run.yaml"


def test_load_parameters_json_rejects_path_escape() -> None:
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
    with pytest.raises(RunRequestError):
        load_parameters_json(raw)


def test_load_parameters_json_accepts_inline_mode_without_repo() -> None:
    raw = (
        '{"run_mode":"inline",'
        '"engine":"shell",'
        '"entrypoint":["/bin/sh","-lc","nvidia-smi"],'
        '"config":null,'
        '"inputs":{},'
        '"env":{},'
        '"outputs_prefix":null}'
    )
    request = load_parameters_json(raw)
    assert request.run_mode == "inline"
    assert request.repo_url is None
    assert request.ref is None


def test_load_parameters_json_rejects_repo_mode_without_repo_fields() -> None:
    raw = (
        '{"run_mode":"repo",'
        '"engine":"shell",'
        '"entrypoint":["/bin/sh","-lc","echo ok"],'
        '"config":null,'
        '"inputs":{},'
        '"env":{},"outputs_prefix":null}'
    )
    with pytest.raises(RunRequestError):
        load_parameters_json(raw)
