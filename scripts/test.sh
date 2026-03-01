#!/usr/bin/env bash
set -euo pipefail

uv run pytest --cov=comic_identity_engine --cov-report=xml --cov-report=term-missing
