#!/usr/bin/env bash
set -euo pipefail

# Ensure we're using the project's virtual environment
export VIRTUAL_ENV="$PWD/.venv"
export PATH="$PWD/.venv/bin:$PATH"

uv run ruff check .
uv run ruff format --check .
