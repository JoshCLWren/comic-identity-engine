#!/usr/bin/env bash
set -euo pipefail

# Ensure we're using the project's virtual environment
export VIRTUAL_ENV="$PWD/.venv"
export PATH="$PWD/.venv/bin:$PATH"

uv run pytest --cov=comic_identity_engine --cov-report=xml --cov-report=term-missing
