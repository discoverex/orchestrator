#!/usr/bin/env bash

run_ops_ci() {
  uvx ruff check --fix .
  uvx ruff format .
  uv run mypy
  uv run pytest -q
}
